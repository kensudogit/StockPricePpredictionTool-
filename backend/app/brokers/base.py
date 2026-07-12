"""Broker adapters: JP (SBI / Rakuten / au Kabukom) + overseas (IBKR / Alpaca)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.config import get_settings


@dataclass
class BrokerOrderRequest:
    ticker: str
    side: str  # buy | sell
    quantity: float
    order_type: str = "market"
    limit_price: float | None = None


@dataclass
class BrokerOrderResult:
    broker: str
    status: str
    broker_order_id: str | None
    raw: dict[str, Any]


class BrokerClient(ABC):
    name: str

    @abstractmethod
    async def place_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        raise NotImplementedError

    @abstractmethod
    async def health(self) -> bool:
        raise NotImplementedError


class PaperBroker(BrokerClient):
    name = "paper"

    async def health(self) -> bool:
        return True

    async def place_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        return BrokerOrderResult(
            broker=self.name,
            status="filled",
            broker_order_id=f"paper-{req.ticker}-{req.side}",
            raw={"qty": req.quantity, "type": req.order_type},
        )


class AlpacaBroker(BrokerClient):
    name = "alpaca"

    def __init__(self) -> None:
        self.settings = get_settings()

    async def health(self) -> bool:
        return bool(self.settings.alpaca_api_key and self.settings.alpaca_api_secret)

    async def place_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        if not await self.health():
            return BrokerOrderResult(self.name, "unconfigured", None, {})
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest

            client = TradingClient(
                self.settings.alpaca_api_key,
                self.settings.alpaca_api_secret,
                paper=self.settings.trading_mode != "live",
            )
            side = OrderSide.BUY if req.side == "buy" else OrderSide.SELL
            order = client.submit_order(
                MarketOrderRequest(
                    symbol=req.ticker.replace(".T", ""),
                    qty=req.quantity,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                )
            )
            return BrokerOrderResult(self.name, str(order.status), str(order.id), {"symbol": req.ticker})
        except Exception as e:
            return BrokerOrderResult(self.name, "error", None, {"error": str(e)})


class IBKRBroker(BrokerClient):
    name = "ibkr"

    async def health(self) -> bool:
        return bool(get_settings().ibkr_host)

    async def place_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        # Requires TWS/Gateway + ib_insync in live setups
        return BrokerOrderResult(
            self.name,
            "stub",
            None,
            {"note": "Connect Interactive Brokers TWS/Gateway and wire ib_insync"},
        )


class SBIBroker(BrokerClient):
    name = "sbi"

    async def health(self) -> bool:
        return bool(get_settings().sbi_api_key)

    async def place_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        return BrokerOrderResult(
            self.name,
            "stub",
            None,
            {"note": "SBI証券 API 契約後にエンドポイントを接続"},
        )


class RakutenBroker(BrokerClient):
    name = "rakuten"

    async def health(self) -> bool:
        return bool(get_settings().rakuten_api_key)

    async def place_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        return BrokerOrderResult(
            self.name,
            "stub",
            None,
            {"note": "楽天証券 API 契約後にエンドポイントを接続"},
        )


class KabucomBroker(BrokerClient):
    name = "kabucom"

    async def health(self) -> bool:
        return bool(get_settings().kabucom_api_password)

    async def place_order(self, req: BrokerOrderRequest) -> BrokerOrderResult:
        # auカブコム kabu STATION API is documented; requires local push/API password
        return BrokerOrderResult(
            self.name,
            "stub",
            None,
            {"note": "auカブコム kabu STATION API を設定してください"},
        )


def get_broker(name: str | None = None) -> BrokerClient:
    settings = get_settings()
    name = (name or settings.broker_name or "paper").lower()
    mapping = {
        "paper": PaperBroker,
        "alpaca": AlpacaBroker,
        "ibkr": IBKRBroker,
        "sbi": SBIBroker,
        "rakuten": RakutenBroker,
        "kabucom": KabucomBroker,
    }
    return mapping.get(name, PaperBroker)()


async def list_broker_status() -> list[dict]:
    out = []
    for name in ("paper", "alpaca", "ibkr", "sbi", "rakuten", "kabucom"):
        b = get_broker(name)
        out.append({"name": name, "available": await b.health()})
    return out
