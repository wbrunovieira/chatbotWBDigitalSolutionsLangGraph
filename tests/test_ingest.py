"""KB ingestion: heading-aware chunking + idempotent, content-addressed upsert."""

import ingest


class FakeQdrant:
    """Minimal in-memory stand-in for the bits of QdrantClient that ingest uses."""

    def __init__(self, exists=False):
        self._exists = exists
        self.points = {}  # id -> payload

    def collection_exists(self, collection_name):
        return self._exists

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

    def test_first_chunked_ingest_prunes_legacy_single_doc_point(self, tmp_path):
        # The exact prod migration: prod's company_info currently holds ONE point at id=1
        # with the legacy {"company_info": ...} payload. The first chunked ingest must
        # replace it with chunks AND delete id=1, not leave it as a stale duplicate.
        kb = tmp_path / "kb.md"
        kb.write_text(MD)
        client = FakeQdrant(exists=True)
        client.points[1] = {"company_info": "old whole document"}

        result = ingest.ingest_company_info(client, path=str(kb), embed_fn=fake_embed)

        assert result["skipped"] is False
        assert 1 not in client.points                       # legacy point pruned
        assert all("text" in p for p in client.points.values())
        assert len(client.points) == len(ingest.chunk_document(MD))

    def test_model_swap_forces_reingest(self, tmp_path):
        # Same KB text, different embedding model -> different ids -> not skipped, and the
        # old-model points are pruned (guards against serving stale vectors after a swap).
        kb = tmp_path / "kb.md"
        kb.write_text(MD)
        client = FakeQdrant()
        ingest.ingest_company_info(client, path=str(kb), embed_fn=fake_embed, model_tag="model-A")
        ids_a = set(client.points)

        result = ingest.ingest_company_info(client, path=str(kb), embed_fn=fake_embed, model_tag="model-B")

        assert result["skipped"] is False
        assert result["pruned"] == len(ids_a)               # every old-model point pruned
        assert set(client.points).isdisjoint(ids_a)         # entirely new id set

    def test_existing_ids_walks_all_scroll_pages(self, tmp_path):
        # _existing_ids must follow scroll pagination; a client that returns ids across two
        # pages must not have the second page dropped (which would cause false re-upserts).
        kb = tmp_path / "kb.md"
        kb.write_text(MD)
        client = FakeQdrant()
        ingest.ingest_company_info(client, path=str(kb), embed_fn=fake_embed)
        all_ids = set(client.points)

        paged = _PagedQdrant(all_ids)
        assert ingest._existing_ids(paged) == all_ids
        assert paged.pages_served >= 2                       # pagination actually exercised


class _PagedQdrant:
    """Serves ids across two scroll pages to exercise the pagination loop in _existing_ids."""

    def __init__(self, ids):
        self._ids = list(ids)
        self.pages_served = 0

    def scroll(self, collection_name, limit, offset, with_payload, with_vectors):
        start = offset or 0
        page = self._ids[start:start + 1]                   # one id per page
        self.pages_served += 1
        next_offset = start + 1 if start + 1 < len(self._ids) else None
        return [type("P", (), {"id": i})() for i in page], next_offset
