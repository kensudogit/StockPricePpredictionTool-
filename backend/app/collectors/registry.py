from app.collectors.alphavantage import AlphaVantageProvider
from app.collectors.base import MarketDataProvider
from app.collectors.finnhub import FinnhubProvider
from app.collectors.polygon import PolygonProvider
from app.collectors.stooq import StooqProvider
from app.collectors.twelve_data import TwelveDataProvider
from app.collectors.yahoo import YahooFinanceProvider
from app.config import get_settings

# Macro / index codes used across the system
MACRO_SERIES = {
    "NIKKEI": "^N225",
    "TOPIX": "^TOPX",
    "SP500": "^GSPC",
    "NASDAQ": "^IXIC",
    "VIX": "^VIX",
    "USDJPY": "USDJPY=X",
    "WTI": "CL=F",
    "US10Y": "^TNX",
}


def get_providers() -> list[MarketDataProvider]:
    """Return configured providers.

    Yahoo chart API first (works from many cloud hosts); Stooq as secondary for JP.
    """
    settings = get_settings()
    providers: list[MarketDataProvider] = [YahooFinanceProvider(), StooqProvider()]
    if settings.alpha_vantage_api_key:
        providers.append(AlphaVantageProvider())
    if settings.polygon_api_key:
        providers.append(PolygonProvider())
    if settings.finnhub_api_key:
        providers.append(FinnhubProvider())
    if settings.twelve_data_api_key:
        providers.append(TwelveDataProvider())
    return providers


def get_primary_provider() -> MarketDataProvider:
    providers = get_providers()
    return providers[0]
