"""Align pybit signing timestamps with Bybit server (/v5/market/time).

Windows clocks often run slightly fast; ErrCode 10002 otherwise repeats until recv_window is huge.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

_logger = logging.getLogger(__name__)

_time_offset_ms: int = 0


def fetch_bybit_server_time_ms(api_base_url: str, timeout_s: float = 15.0) -> int:
    """Return server time in ms for the REST host used by the session."""
    url = f"{api_base_url.rstrip('/')}/v5/market/time"
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("retCode"):
        raise ValueError(payload.get("retMsg", payload))
    result = payload["result"]
    nano = result.get("timeNano")
    if nano is not None and str(nano).strip():
        return int(nano) // 1_000_000
    sec = result["timeSecond"]
    return int(sec) * 1000


def ensure_pybit_timestamp_aligned(api_base_url: str) -> int:
    """
    Patch pybit._helpers.generate_timestamp() to use server-aligned ms time.
    Returns applied offset (server_ms - local_ms), or 0 if sync failed.
    """
    global _time_offset_ms
    import pybit._helpers as pybit_helpers

    try:
        server_ms = fetch_bybit_server_time_ms(api_base_url)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as exc:
        _logger.warning("Bybit server time sync skipped: %s", exc)
        return 0

    local_ms = int(time.time() * 1000)
    _time_offset_ms = server_ms - local_ms
    if abs(_time_offset_ms) > 250:
        _logger.warning(
            "PC clock vs Bybit server by ~%s ms — applying offset to API timestamps. "
            "Enable Windows time sync (NTP) to reduce drift.",
            _time_offset_ms,
        )

    def generate_timestamp_aligned() -> int:
        return int(time.time() * 1000) + _time_offset_ms

    pybit_helpers.generate_timestamp = generate_timestamp_aligned
    return _time_offset_ms
