#!/usr/bin/env bash
#
# chatlogs.sh — inspect and clean the production Qdrant `chat_logs` collection.
#
# Qdrant is only reachable on the internal Docker network (never published to the
# host), so this pipes a self-contained Python program over SSH into the
# `chatbot_app` container — the one process that sits on that network. No deploy is
# needed: the program travels on stdin, it does not have to exist inside the image.
#
# Usage:
#   ops/chatlogs.sh report                 # total, per-day breakdown, unique users, last 15 messages
#   ops/chatlogs.sh purge-user <user_id>   # delete every point for one user_id (e.g. a test session)
#   ops/chatlogs.sh purge-all CONFIRM      # wipe ALL chat_logs (refuses without the literal CONFIRM)
#
# Overridable via env: CHATLOGS_SSH_HOST (default contabo1), CHATLOGS_CONTAINER (default chatbot_app).
set -euo pipefail

HOST="${CHATLOGS_SSH_HOST:-contabo1}"
CONTAINER="${CHATLOGS_CONTAINER:-chatbot_app}"
CMD="${1:-report}"
ARG="${2:-}"

# -i keeps stdin open so the container's `python -` reads the heredoc as its program;
# the subcommand/argument travel as env vars so they never collide with that stdin.
ssh "$HOST" "docker exec -i -e CL_CMD='$CMD' -e CL_ARG='$ARG' $CONTAINER python -" <<'PY' 2>&1 \
  | grep -vE "WARNING: connection|vulnerable|openssh\.com|UserWarning|_client =|INFO:httpx|version check|incompatible|Api key is used"
import os
from collections import Counter
from datetime import datetime, timezone

from rag.db import get_qdrant_client

COLL = "chat_logs"
cmd = os.environ.get("CL_CMD", "report")
arg = os.environ.get("CL_ARG", "")
c = get_qdrant_client()


def fmt(ts):
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(ts)


if cmd == "report":
    total = c.count(COLL, exact=True).count
    print(f"total points: {total}")
    if total:
        pts, _ = c.scroll(COLL, limit=10000, with_payload=True, with_vectors=False)
        rows = [
            (
                (p.payload or {}).get("timestamp"),
                (p.payload or {}).get("user_id"),
                (p.payload or {}).get("current_page"),
                str((p.payload or {}).get("user_input") or "")[:80],
            )
            for p in pts
        ]
        rows.sort(key=lambda r: r[0] or 0)
        days = Counter(fmt(r[0])[:10] for r in rows if r[0])
        print("\nby day:")
        for d in sorted(days):
            print(f"  {d}  {days[d]}")
        print(f"\nunique user_ids: {len(Counter(r[1] for r in rows))}")
        print("\nlast 15 messages:")
        for ts, uid, page, msg in rows[-15:]:
            print(f"  {fmt(ts)} | {uid} | {page} | {msg}")

elif cmd == "purge-user":
    from qdrant_client import models

    if not arg:
        raise SystemExit("purge-user requires a user_id as the 2nd argument")
    flt = models.Filter(must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=arg))])
    matched = c.count(COLL, count_filter=flt, exact=True).count
    c.delete(COLL, points_selector=models.FilterSelector(filter=flt))
    print(f"purge-user {arg}: matched {matched}, total now {c.count(COLL, exact=True).count}")

elif cmd == "purge-all":
    from qdrant_client import models

    if arg != "CONFIRM":
        raise SystemExit("refusing: pass CONFIRM as the 2nd argument to wipe ALL chat_logs")
    was = c.count(COLL, exact=True).count
    ids, offset = [], None
    while True:
        pts, offset = c.scroll(COLL, limit=1000, with_payload=False, with_vectors=False, offset=offset)
        ids.extend(p.id for p in pts)
        if offset is None:
            break
    if ids:
        c.delete(COLL, points_selector=models.PointIdsList(points=ids))
    print(f"purge-all: was {was}, now {c.count(COLL, exact=True).count}")

else:
    raise SystemExit(f"unknown command: {cmd!r} (use report | purge-user <id> | purge-all CONFIRM)")
PY
