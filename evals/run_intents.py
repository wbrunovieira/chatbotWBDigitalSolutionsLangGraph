"""
Offline eval: run the intent classifier over evals/intents.jsonl and report accuracy.

Exercises the REAL path — the canonical detect_intent prompt (single source) + the same
response_format gating and parse_intent used in production — against the labelled set,
including the production failures from the log analysis ("boa tarde", "vcs fazem
automassao?").

Calls the DeepSeek API, so it needs a real key. Run locally or in a gated CI job:

    DEEPSEEK_API_KEY=... python evals/run_intents.py [--threshold 0.9]

Exits non-zero if accuracy < threshold, so it can gate a build (this is what #11 wires
into CI).
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so `python evals/run_intents.py` finds the root modules

import _deepseek  # noqa: E402 — evals/_deepseek.py (resilient DeepSeek call)
from langfuse_client import LOCAL_PROMPTS, LocalPrompt  # noqa: E402
from nodes import parse_intent  # noqa: E402


def classify(message: str, language: str, current_page: str = "/") -> str:
    tmpl = LOCAL_PROMPTS["detect_intent"]
    prompt = LocalPrompt("detect_intent", tmpl["template"], tmpl["type"]).compile(
        user_input=message, language=language, current_page=current_page
    )
    body = {
        "model": "deepseek-v4-flash",  # NB: a floating vendor pointer — weights can change server-side
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,  # deterministic, so a gate red means a real change, not sampling noise
    }
    if "json" in prompt.lower():
        body["response_format"] = {"type": "json_object"}
    data = _deepseek.chat(body)
    content = data["choices"][0]["message"]["content"]
    return parse_intent(content)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.9)
    ap.add_argument("--dataset", default=str(ROOT / "evals" / "intents.jsonl"))
    args = ap.parse_args()

    rows = [json.loads(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()]
    passed, fails = 0, []
    try:
        for r in rows:
            got = classify(r["message"], r.get("language", "pt-BR"))
            if got == r["expected"]:
                passed += 1
            else:
                fails.append((r["message"], r["expected"], got))
    except _deepseek.InfraError as e:
        # Infra problem, NOT a quality regression — exit 2 so a red build is legible & re-runnable.
        print(f"::error::eval aborted (infra, not a regression): {e}")
        return 2

    accuracy = passed / len(rows) if rows else 0.0
    print(f"intent accuracy: {passed}/{len(rows)} = {accuracy:.1%}")
    for message, expected, got in fails:
        print(f"  FAIL: {message!r}  expected={expected}  got={got}")

    if accuracy < args.threshold:
        print(f"BELOW THRESHOLD ({args.threshold:.0%}) — failing the build")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
