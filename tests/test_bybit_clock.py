from __future__ import annotations

import json

from matryoshka_bot.exchange import bybit_clock


def test_fetch_bybit_server_time_ms_from_second(monkeypatch) -> None:
    payload = {"retCode": 0, "result": {"timeSecond": "1700000500"}}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(bybit_clock.urllib.request, "urlopen", lambda *a, **k: Resp())
    assert bybit_clock.fetch_bybit_server_time_ms("https://api-demo.bybit.com") == 1_700_000_500_000


def test_ensure_pybit_timestamp_aligned_matches_server(monkeypatch) -> None:
    server_ms = 1_777_585_988_521
    local_wall_s = 1_777_585_989.700

    monkeypatch.setattr(bybit_clock, "fetch_bybit_server_time_ms", lambda _url: server_ms)

    monkeypatch.setattr(bybit_clock.time, "time", lambda: local_wall_s)

    off = bybit_clock.ensure_pybit_timestamp_aligned("https://api-demo.bybit.com")
    expected_off = server_ms - int(local_wall_s * 1000)
    assert off == expected_off

    import pybit._helpers as pybit_helpers

    assert pybit_helpers.generate_timestamp() == server_ms
