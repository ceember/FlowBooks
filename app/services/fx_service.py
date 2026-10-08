"""Bank of Canada Valet FX rate fetcher.

BoC publishes daily noon-rate observations via the public Valet API:
    https://www.bankofcanada.ca/valet/observations/FX{FROM}{TO}/json?recent=1

Historically BoC only publishes pairs where one leg is CAD (FXUSDCAD,
FXEURCAD, etc.). For pairs that don't include CAD, we cross-rate via CAD:
    rate(EUR -> USD) = rate(EUR -> CAD) / rate(USD -> CAD)

All failures (timeouts, 404s, missing observations, JSON shape changes)
return a result with rate=None so the API layer can degrade gracefully
without raising — the frontend falls back to 1.0 with a notice.
"""

import json
import urllib.request
import urllib.error
from decimal import Decimal
from typing import Optional

VALET_BASE = "https://www.bankofcanada.ca/valet/observations"
TIMEOUT_SECONDS = 5


def _fetch_direct(from_code: str, to_code: str) -> Optional[dict]:
    """Try a direct BoC series like FXUSDCAD. Returns dict or None on any failure."""
    series = f"FX{from_code}{to_code}"
    url = f"{VALET_BASE}/{series}/json?recent=1"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "SlowBooks-Pro-2026/1.0"}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            if resp.status != 200:
                return None
            payload = json.loads(resp.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
    ):
        return None

    observations = payload.get("observations") or []
    if not observations:
        return None
    obs = observations[-1]
    date = obs.get("d")
    cell = obs.get(series) or {}
    raw = cell.get("v")
    if raw in (None, ""):
        return None
    try:
        rate = Decimal(str(raw))
    except Exception:
        return None
    return {"rate": rate, "observation_date": date, "series": series}


def get_rate(from_code: str, to_code: str) -> dict:
    """Resolve a rate from `from_code` to `to_code`. Same currency = 1.

    Tries the direct BoC series, then a CAD cross-rate. Returns:
        {"rate": Decimal | None, "observation_date": str | None,
         "source": "bankofcanada-direct" | "bankofcanada-cross" | None,
         "error": str | None}
    """
    f = (from_code or "").upper()
    t = (to_code or "").upper()
    if not f or not t:
        return {
            "rate": None,
            "observation_date": None,
            "source": None,
            "error": "missing currency code",
        }
    if f == t:
        return {
            "rate": Decimal("1"),
            "observation_date": None,
            "source": "identity",
            "error": None,
        }

    direct = _fetch_direct(f, t)
    if direct:
        return {
            "rate": direct["rate"],
            "observation_date": direct["observation_date"],
            "source": "bankofcanada-direct",
            "error": None,
        }

    # Cross via CAD: rate(F -> T) = rate(F -> CAD) / rate(T -> CAD)
    if f != "CAD" and t != "CAD":
        leg1 = _fetch_direct(f, "CAD")
        leg2 = _fetch_direct(t, "CAD")
        if leg1 and leg2 and leg2["rate"] != 0:
            cross = (leg1["rate"] / leg2["rate"]).quantize(Decimal("0.00000001"))
            obs = (
                min(leg1["observation_date"] or "", leg2["observation_date"] or "")
                or None
            )
            return {
                "rate": cross,
                "observation_date": obs,
                "source": "bankofcanada-cross",
                "error": None,
            }

    return {
        "rate": None,
        "observation_date": None,
        "source": None,
        "error": "rate unavailable",
    }
