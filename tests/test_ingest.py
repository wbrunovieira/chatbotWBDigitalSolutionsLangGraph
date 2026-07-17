"""KB ingestion: heading-aware chunking + idempotent, content-addressed upsert."""

import ingest


class FakeQdrant:
    """Minimal in-memory stand-in for the bits of QdrantClient that ingest uses."""

    def __init__(self, exists=False):
        self._exists = exists
        self.points = {}  # id -> payload

    def get_collection(self, collection_name):
        if not self._exists:
            raise RuntimeError("missing")
        return object()

    def create_collection(self, collection_name, vectors_config):
        self._exists = True

    def scroll(self, collection_name, limit, offset, with_payload, with_vectors):
        pts = [type("P", (), {"id": pid})() for pid in self.points]
        return pts, None  # single page

    def upsert(self, collection_name, points):
        self._exists = True
        for p in points:
            self.points[p.id] = p.payload

    def delete(self, collection_name, points_selector):
        for pid in points_selector:
            self.points.pop(pid, None)


def fake_embed(text):
    return [float(len(text) % 7)] * ingest.VECTOR_SIZE


MD = """## A
alpha body one.

### A1
alpha one detail.

---

## B
beta body.
"""


class TestChunkDocument:
    def test_heading_aware_sections_and_prefix(self):
        chunks = ingest.chunk_document(MD)
        sections = [c["section"] for c in chunks]
        assert "A" in sections
        assert "A > A1" in sections          # nested heading path
        assert "B" in sections
        # each chunk is prefixed with its section so a retrieved passage is self-describing
        for c in chunks:
            assert c["text"].startswith(c["section"])

    def test_respects_max_chars(self):
        big = "## Big\n\n" + ("word " * 2000)
        chunks = ingest.chunk_document(big, max_chars=500)
        assert len(chunks) > 1
        assert all(len(c["text"]) <= 500 + len(c["section"]) + 2 for c in chunks)

    def test_chunk_ids_are_stable_and_unique(self):
        chunks = ingest.chunk_document(MD)
        ids1 = [ingest._chunk_id(c) for c in chunks]
        ids2 = [ingest._chunk_id(c) for c in chunks]
        assert ids1 == ids2                  # deterministic
        assert len(set(ids1)) == len(ids1)   # collision-free for this doc


class TestIngestIdempotency:
    def test_first_run_upserts_all_chunks(self, tmp_path):
        kb = tmp_path / "kb.md"
        kb.write_text(MD)
        client = FakeQdrant()
        result = ingest.ingest_company_info(client, path=str(kb), embed_fn=fake_embed)
        assert result["skipped"] is False
        assert result["chunks"] == len(ingest.chunk_document(MD))
        assert len(client.points) == result["chunks"]
        assert all("text" in p and "section" in p for p in client.points.values())

    def test_second_run_same_content_is_skipped(self, tmp_path):
        kb = tmp_path / "kb.md"
        kb.write_text(MD)
        client = FakeQdrant()
        ingest.ingest_company_info(client, path=str(kb), embed_fn=fake_embed)
        before = dict(client.points)
        result = ingest.ingest_company_info(client, path=str(kb), embed_fn=fake_embed)
        assert result["skipped"] is True
        assert client.points == before        # no churn

    def test_changed_content_prunes_stale_points(self, tmp_path):
        kb = tmp_path / "kb.md"
        kb.write_text(MD)
        client = FakeQdrant()
        ingest.ingest_company_info(client, path=str(kb), embed_fn=fake_embed)
        first_ids = set(client.points)

        kb.write_text(MD.replace("beta body.", "beta body COMPLETELY rewritten."))
        result = ingest.ingest_company_info(client, path=str(kb), embed_fn=fake_embed)

        assert result["skipped"] is False
        assert result["pruned"] >= 1
        # the old "B" chunk id is gone, not left behind as a duplicate
        assert first_ids != set(client.points)
        assert len(client.points) == len(ingest.chunk_document(kb.read_text()))
