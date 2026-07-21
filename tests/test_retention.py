"""chat_logs retention: delete points older than the window (#357)."""

import time

from rag import retention


class FakeClient:
    def __init__(self, count=0):
        self._count = count
        self.deleted_selector = None

    def count(self, collection_name, count_filter):
        return type("C", (), {"count": self._count})()

    def delete(self, collection_name, points_selector):
        self.deleted_selector = points_selector


class TestPurgeOldChatLogs:
    def test_deletes_points_older_than_cutoff(self):
        client = FakeClient(count=7)
        result = retention.purge_old_chat_logs(client, retention_days=30)

        assert result["deleted"] == 7
        assert result["retention_days"] == 30
        assert abs(result["cutoff"] - (int(time.time()) - 30 * 86400)) < 5
        # the delete matches (timestamp < cutoff) OR (timestamp missing) via a `should` filter
        conds = client.deleted_selector.should
        range_cond = next(c for c in conds if getattr(c, "range", None) is not None)
        assert range_cond.key == "timestamp"
        assert range_cond.range.lt == result["cutoff"]
        empty_cond = next(c for c in conds if getattr(c, "is_empty", None) is not None)
        assert empty_cond.is_empty.key == "timestamp"

    def test_noop_when_nothing_is_old(self):
        client = FakeClient(count=0)
        result = retention.purge_old_chat_logs(client, retention_days=90)
        assert result["deleted"] == 0
        assert client.deleted_selector is None  # delete not called when there's nothing to purge
