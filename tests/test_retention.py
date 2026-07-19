"""chat_logs retention: delete points older than the window (#357)."""

import time

import retention


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
        # the delete used a `timestamp < cutoff` range filter
        cond = client.deleted_selector.must[0]
        assert cond.key == "timestamp"
        assert cond.range.lt == result["cutoff"]

    def test_noop_when_nothing_is_old(self):
        client = FakeClient(count=0)
        result = retention.purge_old_chat_logs(client, retention_days=90)
        assert result["deleted"] == 0
        assert client.deleted_selector is None  # delete not called when there's nothing to purge
