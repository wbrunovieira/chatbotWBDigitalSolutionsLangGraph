"""
Tool-use eval: does the model pick the RIGHT tool (or none) on labelled action messages?

Calls DeepSeek with the real tool specs + the agent's tool system prompt, and checks which
tool the model decides to call first (or None). `expected_tool` may be pipe-separated for
cases where more than one tool is acceptable; null means "no tool — just answer".

Needs a real key. Run locally or in a gated CI job:
    DEEPSEEK_API_KEY=... python evals/run_tools.py [--threshold 0.8]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nodes import TOOL_SYSTEM_PROMPT  # noqa: E402
from tools import TOOL_SPECS  # noqa: E402


def picked_tool(message: str):
    body = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": TOOL_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        "tools": TOOL_SPECS,
        "tool_choice": "auto",
        "temperature": 0.2,
    }
    resp = httpx.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}", "Content-Type": "application/json"},
        json=body,
        timeout=30.0,
    )
    msg = resp.json()["choices"][0]["message"]
    calls = msg.get("tool_calls") or []
    return calls[0]["function"]["name"] if calls else None


def is_ok(expected, got) -> bool:
    if expected is None:
        return got is None
    return got in set(expected.split("|"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.8)
    ap.add_argument("--dataset", default=str(ROOT / "evals" / "tools.jsonl"))
    args = ap.parse_args()

    rows = [json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()]
    passed, fails = 0, []
    for r in rows:
        got = picked_tool(r["message"])
        if is_ok(r["expected_tool"], got):
            passed += 1
        else:
            fails.append((r["message"], r["expected_tool"], got))

    accuracy = passed / len(rows) if rows else 0.0
    print(f"tool-selection accuracy: {passed}/{len(rows)} = {accuracy:.1%}")
    for message, expected, got in fails:
        print(f"  FAIL: {message!r}  expected={expected}  got={got}")

    if accuracy < args.threshold:
        print(f"BELOW THRESHOLD ({args.threshold:.0%}) — failing the build")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
