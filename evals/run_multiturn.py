"""
Multi-turn eval (#21): agency + memory across a whole conversation.

Runs each scripted conversation turn-by-turn through the REAL tool specs + agent system
prompt, accumulating the history (user + assistant + synthetic tool results) so the model
must USE prior turns to act — e.g. "quero um" only makes sense given the earlier "vocês
criam sites?". At each turn we assert the model calls the expected tool (or none), proving
the lead-capture happy path (greeting -> question -> capture -> schedule) works across turns,
not just on isolated single messages (that is run_tools.py's job).

`expect_tool` may be pipe-separated (more than one acceptable); null means "no tool — answer".
Needs a real key. Run locally or in a gated CI job:

    DEEPSEEK_API_KEY=... python evals/run_multiturn.py [--threshold 0.8]
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import _deepseek  # noqa: E402 — evals/_deepseek.py (resilient DeepSeek call)
from nodes import TOOL_SYSTEM_PROMPT  # noqa: E402
from tools import TOOL_SPECS  # noqa: E402


def _pick_tool(messages: list):
    body = {
        "model": "deepseek-chat",
        "messages": messages,
        "tools": TOOL_SPECS,
        "tool_choice": "auto",
        "temperature": 0,  # deterministic, so a red gate is a real change not sampling noise
    }
    msg = _deepseek.chat(body)["choices"][0]["message"]
    calls = msg.get("tool_calls") or []
    return (calls[0]["function"]["name"] if calls else None), msg


def _ok(expected, got) -> bool:
    if expected is None:
        return got is None
    return got in set(expected.split("|"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.8)
    ap.add_argument("--dataset", default=str(ROOT / "evals" / "multiturn.jsonl"))
    args = ap.parse_args()

    convos = [json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()]
    total, passed, fails = 0, 0, []
    try:
        for convo in convos:
            messages = [{"role": "system", "content": TOOL_SYSTEM_PROMPT}]
            for turn in convo["turns"]:
                messages.append({"role": "user", "content": turn["user"]})
                got, msg = _pick_tool(messages)
                total += 1
                if _ok(turn["expect_tool"], got):
                    passed += 1
                else:
                    fails.append((convo["name"], turn["user"], turn["expect_tool"], got))
                # Carry the turn forward so the next one has context. Feed a synthetic tool
                # result when a tool was called, so the model can continue the conversation.
                if got:
                    messages.append({"role": "assistant", "content": msg.get("content"),
                                     "tool_calls": msg.get("tool_calls")})
                    for call in msg.get("tool_calls") or []:
                        messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                         "content": '{"ok": true}'})
                else:
                    messages.append({"role": "assistant", "content": msg.get("content") or "Claro!"})
    except _deepseek.InfraError as e:
        print(f"::error::eval aborted (infra, not a regression): {e}")
        return 2

    accuracy = passed / total if total else 0.0
    print(f"multi-turn tool accuracy: {passed}/{total} = {accuracy:.1%}")
    for name, user, expected, got in fails:
        print(f"  FAIL [{name}]: {user!r}  expected={expected}  got={got}")

    if accuracy < args.threshold:
        print(f"BELOW THRESHOLD ({args.threshold:.0%}) — failing the build")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
