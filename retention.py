"""
chat_logs data retention (LGPD/GDPR).

Qdrant has no per-point TTL, so this deletes chat_logs points older than
CHAT_LOGS_RETENTION_DAYS by a range filter on the stored `timestamp` payload (unix seconds,
written by save_log_qdrant). Run on a schedule (see the Ansible cron), e.g. daily:

    docker exec chatbot_app python retention.py

PII in the stored copy is already redacted at write time (guardrails.redact_pii); this bounds
how long even the redacted record is kept.
"""

import logging
import time

from qdrant_client.http.models import FieldCondition, Filter, Range

from config import CHAT_LOGS_RETENTION_DAYS


def purge_old_chat_logs(client, retention_days: int = None) -> dict:
    """Delete chat_logs points whose `timestamp` is older than the retention window."""
    retention_days = CHAT_LOGS_RETENTION_DAYS if retention_days is None else retention_days
    cutoff = int(time.time()) - retention_days * 86400
    stale = Filter(must=[FieldCondition(key="timestamp", range=Range(lt=cutoff))])

    before = client.count(collection_name="chat_logs", count_filter=stale).count
    if before:
        client.delete(collection_name="chat_logs", points_selector=stale)
    logging.info("retention: deleted %d chat_logs points older than %d days", before, retention_days)
    return {"deleted": before, "retention_days": retention_days, "cutoff": cutoff}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from db import get_qdrant_client

    print(purge_old_chat_logs(get_qdrant_client()))
