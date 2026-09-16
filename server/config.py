from __future__ import annotations

from copy import deepcopy

DEFAULT_TRADE_CONFIG: dict[str, float] = {
    "buy_threshold_points": 0.0,
    "sell_threshold_points": 0.0,
    "buy_sl_points": 1000.0,
    "sell_sl_points": 1000.0,
    "risk_percent": 1.0,
    "max_volume": 1.0,
    "tp_multiplier": 2.0,
    "buy_sl_required": 1.0,
    "sell_sl_required": 1.0,
    "tp_profit_rate_percent": 2.0,
}

SYMBOL_TRADE_CONFIG: dict[str, dict[str, float]] = {
    "XAUUSDc": {
        "buy_threshold_points": 500.0,
        "sell_threshold_points": 500.0,
        "buy_sl_points": 5000.0,
        "sell_sl_points": 5000.0,
        "risk_percent": 0.25,
        "max_volume": 1.0,
        "tp_multiplier": 2.0,
        "buy_sl_required": 1.0,
        "sell_sl_required": 1.0,
        "tp_profit_rate_percent": 2.0,
    },
    # Add more symbols explicitly, for example:
    # "BTCUSDc": {
    #     "buy_threshold_points": 1000.0,
    #     "sell_threshold_points": 1000.0,
    #     "buy_sl_points": 10000.0,
    #     "sell_sl_points": 10000.0,
    #     "risk_percent": 0.1,
    #     "max_volume": 0.5,
    #     "tp_multiplier": 2.0,
    #     "buy_sl_required": 1.0,
    #     "sell_sl_required": 1.0,
    #     "tp_profit_rate_percent": 1.0,
    # },
}

def get_trade_config(symbol: str) -> dict[str, float] | None:
    """Return config for an explicitly allowed symbol; None means symbol is disabled."""
    config = SYMBOL_TRADE_CONFIG.get(symbol)
    return deepcopy(config) if config is not None else None


def get_configured_symbols() -> list[str]:
    """Return symbols allowed to use server-side trading tools."""
    return sorted(SYMBOL_TRADE_CONFIG)
