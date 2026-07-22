"""
Low-credit alert: poll the DeepSeek account balance and WhatsApp the team when it's low.

DeepSeek's /user/balance API returns the account's remaining USD. When it drops below
DEEPSEEK_BALANCE_ALERT_THRESHOLD, notify the team on WhatsApp (via the already-configured
Evolution instance) so someone tops it up before the chatbot goes down for lack of credit —
a failure that would otherwise be silent. Run daily by cron:

    python -m providers.balance
"""

import asyncio
import logging

import httpx

import config
from agents.tools import _notify_team_whatsapp

BALANCE_URL = "https://api.deepseek.com/user/balance"


def get_balance() -> float | None:
    """Return the DeepSeek account's total available USD balance, or None on error."""
    try:
        resp = httpx.get(
            BALANCE_URL,
            headers={"Authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        infos = resp.json().get("balance_infos") or []
        usd = next((b for b in infos if b.get("currency") == "USD"), None)
        return float(usd["total_balance"]) if usd else None
    except Exception as exc:  # noqa: BLE001 — a failed check must never crash the cron
        logging.error("DeepSeek balance check failed: %s", exc)
        return None


async def check_and_alert(threshold: float | None = None) -> dict:
    """Check the balance; WhatsApp the team if it's below the threshold. Meant to run daily:
    it re-alerts each day the balance stays low — a deliberate top-up reminder, not idempotent."""
    threshold = config.DEEPSEEK_BALANCE_ALERT_THRESHOLD if threshold is None else threshold
    balance = get_balance()
    if balance is None:
        return {"ok": False, "balance": None, "alerted": False}

    low = balance < threshold
    if low:
        await _notify_team_whatsapp(
            f"⚠️ DeepSeek: saldo baixo — US$ {balance:.2f} (abaixo de US$ {threshold:.2f}). "
            f"Recarregue para o chatbot não parar por falta de crédito."
        )
        logging.warning("DeepSeek balance LOW: $%.2f < $%.2f — team alerted", balance, threshold)
    else:
        logging.info("DeepSeek balance OK: $%.2f", balance)
    return {"ok": True, "balance": balance, "threshold": threshold, "alerted": low}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(check_and_alert()))
