"""Single live-trading gate. Stubs never reach a real venue."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings

CONFIRM = "I_UNDERSTAND_LIVE_RISK"
IMPLEMENTED_LIVE = frozenset({"alpaca"})
STUB_BROKERS = frozenset({"sbi", "rakuten", "kabucom", "ibkr"})


def live_venue(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    if (s.trading_mode or "paper").lower() != "live":
        return "paper"
    if (s.live_trading_confirm or "").strip() != CONFIRM:
        return "blocked"
    name = (s.broker_name or "paper").lower()
    if name in STUB_BROKERS:
        return "stub_blocked"
    if name == "alpaca" and s.alpaca_api_key.strip() and s.alpaca_api_secret.strip():
        return "alpaca"
    if name == "paper":
        return "paper"
    return "blocked"


def live_trading_allowed(settings: Settings | None = None) -> bool:
    return live_venue(settings) in IMPLEMENTED_LIVE


def can_place(
    *,
    mode: str,
    broker: str,
    settings: Settings | None = None,
) -> tuple[bool, str]:
    """Return (ok, reason) before any broker.place_order."""
    s = settings or get_settings()
    broker = (broker or s.broker_name or "paper").lower()
    mode = (mode or s.trading_mode or "paper").lower()

    if broker in STUB_BROKERS:
        return False, f"broker {broker} is a stub — live/paper place is blocked until wired"

    if mode != "live":
        if broker == "alpaca" and not (s.alpaca_api_key.strip() and s.alpaca_api_secret.strip()):
            if broker != "paper":
                return False, "alpaca keys missing; use broker=paper"
        return True, "ok"

    if (s.live_trading_confirm or "").strip() != CONFIRM:
        return False, "LIVE_TRADING_CONFIRM=I_UNDERSTAND_LIVE_RISK required for live orders"

    if broker == "paper":
        return False, "live mode cannot use paper broker"

    if broker not in IMPLEMENTED_LIVE:
        return False, f"broker {broker} is not an implemented live venue"

    if broker == "alpaca" and not (s.alpaca_api_key.strip() and s.alpaca_api_secret.strip()):
        return False, "ALPACA_API_KEY / ALPACA_API_SECRET required"

    return True, "ok"


def readiness_report(
    settings: Settings | None = None,
    *,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    s = settings or get_settings()
    venue = live_venue(s)
    ok, reason = can_place(mode=s.trading_mode, broker=s.broker_name, settings=s)
    ev_ok = True if evidence is None else bool(evidence.get("ok"))
    return {
        "trading_mode": s.trading_mode,
        "broker_name": s.broker_name,
        "live_venue": venue,
        "live_trading_allowed": live_trading_allowed(s),
        "confirm_set": (s.live_trading_confirm or "").strip() == CONFIRM,
        "paper_fee_bps": s.paper_fee_bps,
        "min_oos_hit_rate": s.min_oos_hit_rate,
        "min_oos_samples": s.min_oos_samples,
        "can_place_default": ok,
        "place_reason": reason,
        "evidence_ok": ev_ok,
        "evidence": evidence,
        "implemented_live": sorted(IMPLEMENTED_LIVE),
        "stub_brokers": sorted(STUB_BROKERS),
    }
