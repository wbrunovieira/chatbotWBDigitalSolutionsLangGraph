"""Low-credit alert: DeepSeek balance check → WhatsApp notify when low."""

import providers.balance as balance


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class TestGetBalance:
    def test_parses_usd_total(self, monkeypatch):
        payload = {"balance_infos": [{"currency": "USD", "total_balance": "9.72"}]}
        monkeypatch.setattr(balance.httpx, "get", lambda *a, **k: _Resp(payload))
        assert balance.get_balance() == 9.72

    def test_none_when_no_usd(self, monkeypatch):
        monkeypatch.setattr(balance.httpx, "get",
                            lambda *a, **k: _Resp({"balance_infos": [{"currency": "CNY", "total_balance": "1"}]}))
        assert balance.get_balance() is None

    def test_none_on_error(self, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("network")
        monkeypatch.setattr(balance.httpx, "get", boom)
        assert balance.get_balance() is None


class TestCheckAndAlert:
    async def test_alerts_when_below_threshold(self, monkeypatch):
        sent = []

        async def fake_notify(text):
            sent.append(text)

        monkeypatch.setattr(balance, "get_balance", lambda: 1.5)
        monkeypatch.setattr(balance, "_notify_team_whatsapp", fake_notify)
        out = await balance.check_and_alert(threshold=2.0)
        assert out == {"ok": True, "balance": 1.5, "threshold": 2.0, "alerted": True}
        assert len(sent) == 1 and "1.50" in sent[0]

    async def test_no_alert_when_above_threshold(self, monkeypatch):
        sent = []

        async def fake_notify(text):
            sent.append(text)

        monkeypatch.setattr(balance, "get_balance", lambda: 9.72)
        monkeypatch.setattr(balance, "_notify_team_whatsapp", fake_notify)
        out = await balance.check_and_alert(threshold=2.0)
        assert out["alerted"] is False and sent == []

    async def test_no_alert_when_balance_unavailable(self, monkeypatch):
        monkeypatch.setattr(balance, "get_balance", lambda: None)
        out = await balance.check_and_alert(threshold=2.0)
        assert out == {"ok": False, "balance": None, "alerted": False}
