from __future__ import annotations

import os

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

def get_trade_config() -> dict[str, float]:
    cfg = DEFAULT_TRADE_CONFIG.copy()
    for key in cfg:
        env_key = f"MT5_{key.upper()}"
        value = os.getenv(env_key)
        if value is not None:
            try:
                cfg[key] = float(value)
            except ValueError:
                pass
    return cfg
