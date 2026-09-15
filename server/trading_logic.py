from __future__ import annotations

from typing import Any, Literal

from server.config import get_trade_config


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_position_side(position: Any) -> str:
    if getattr(position, "type", 0) in (0, 1):
        return "buy" if getattr(position, "type", 0) == 0 else "sell"
    return "buy" if str(getattr(position, "type", "")).lower() in {"buy", "0"} else "sell"


def compute_equilibrium_price(current_price: float, positions: list[Any], side: Literal["buy", "sell"]) -> float:
    """Compute equilibrium using only the same-side group: buy positions for buy logic, sell positions for sell logic."""
    filtered = [pos for pos in positions if _get_position_side(pos) == side]
    if not filtered:
        return current_price

    total_price = 0.0
    total_volume = 0.0
    for pos in filtered:
        volume = _safe_float(getattr(pos, "volume", 0.0), 0.0)
        if volume <= 0:
            continue
        entry = _safe_float(getattr(pos, "price_open", current_price), current_price)
        total_price += entry * volume
        total_volume += volume

    if total_volume <= 0:
        return current_price

    return total_price / total_volume


def check_buy_stoploss_moved(positions: list[Any]) -> bool:
    """Return True when existing buy positions already have stop-loss at or above entry."""
    if not positions:
        return True

    for pos in positions:
        if _get_position_side(pos) != "buy":
            continue
        entry = _safe_float(getattr(pos, "price_open", 0.0), 0.0)
        sl = _safe_float(getattr(pos, "sl", 0.0), 0.0)
        if sl <= 0:
            return False
        if sl < entry:
            return False
    return True


def auto_calculate_volume(
    account_balance: float,
    risk_percent: float,
    stop_distance: float,
    pip_value: float = 10.0,
    max_volume: float = 1.0,
) -> float:
    """Estimate lot volume from a risk percentage and price distance."""
    risk_amount = account_balance * max(risk_percent, 0.0) / 100.0
    if pip_value <= 0:
        pip_value = 10.0
    distance = max(abs(stop_distance), 0.0001)
    volume = risk_amount / (distance * pip_value)
    if volume <= 0:
        return 0.01
    return max(0.01, min(max_volume, round(volume, 2)))


def evaluate_open_signal(
    symbol: str,
    current_price: float,
    positions: list[Any],
    side: Literal["buy", "sell"],
    threshold: float | None = None,
    account_balance: float = 1000.0,
    risk_percent: float | None = None,
    max_volume: float | None = None,
) -> dict[str, Any]:
    """Decision engine matching the MQL OpenOrder logic: same-side equilibrium and internal point-based threshold."""
    config = get_trade_config()
    if threshold is None:
        threshold = config["buy_threshold_points"] if side == "buy" else config["sell_threshold_points"]
    if risk_percent is None:
        risk_percent = config["risk_percent"]
    if max_volume is None:
        max_volume = config["max_volume"]

    equilibrium = compute_equilibrium_price(current_price, positions, side)
    stop_loss_ok = check_buy_stoploss_moved(positions) if side == "buy" else True

    result: dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "equilibrium": equilibrium,
        "threshold": threshold,
        "allowed": False,
        "reason": "",
        "volume": 0.0,
        "entry_price": current_price,
        "stop_loss": current_price,
        "take_profit": current_price,
    }

    if side == "buy":
        if not stop_loss_ok:
            result["reason"] = "Existing buy positions still have stop loss below entry; wait for adjustment."
            return result
        if current_price <= equilibrium + threshold:
            result["reason"] = f"Current price {current_price} is not above equilibrium {equilibrium} + threshold {threshold}."
            return result

        stop_distance = max(current_price - equilibrium, 0.0001)
        volume = auto_calculate_volume(account_balance, risk_percent, stop_distance, pip_value=10.0, max_volume=max_volume)
        result.update(
            {
                "allowed": True,
                "reason": "Buy condition satisfied.",
                "volume": volume,
                "stop_loss": equilibrium,
                "take_profit": current_price + (current_price - equilibrium) * 2.0,
            }
        )
        return result

    if side == "sell":
        if current_price >= equilibrium - threshold:
            result["reason"] = f"Current price {current_price} is not below equilibrium {equilibrium} - threshold {threshold}."
            return result

        stop_distance = max(equilibrium - current_price, 0.0001)
        volume = auto_calculate_volume(account_balance, risk_percent, stop_distance, pip_value=10.0, max_volume=max_volume)
        result.update(
            {
                "allowed": True,
                "reason": "Sell condition satisfied.",
                "volume": volume,
                "stop_loss": equilibrium,
                "take_profit": current_price - (equilibrium - current_price) * 2.0,
            }
        )
        return result

    result["reason"] = "Unsupported side. Use buy or sell."
    return result


def evaluate_tp_signal(
    position: Any,
    current_price: float,
    account_balance: float = 1000.0,
    threshold_rate: float | None = None,
) -> dict[str, Any]:
    """Allow close only when the group profit exceeds the configured rate versus balance."""
    config = get_trade_config()
    threshold_rate = config["tp_profit_rate_percent"] if threshold_rate is None else threshold_rate

    position_type = _get_position_side(position)
    entry = _safe_float(getattr(position, "price_open", current_price), current_price)
    volume = _safe_float(getattr(position, "volume", 0.0), 0.0)
    current_profit = 0.0

    if position_type == "buy":
        current_profit = (current_price - entry) * volume
    else:
        current_profit = (entry - current_price) * volume

    balance = max(account_balance, 1.0)
    profit_rate = (current_profit / balance) * 100.0

    result: dict[str, Any] = {
        "symbol": getattr(position, "symbol", ""),
        "ticket": getattr(position, "ticket", 0),
        "side": position_type,
        "current_price": current_price,
        "profit": current_profit,
        "profit_rate_percent": profit_rate,
        "threshold_rate_percent": threshold_rate,
        "allowed": False,
        "reason": "",
    }

    if current_profit <= 0:
        result["reason"] = "Position has not profit yet."
        return result

    if profit_rate >= threshold_rate:
        result["allowed"] = True
        result["reason"] = f"Profit rate {profit_rate:.2f}% is above threshold {threshold_rate:.2f}%."
        return result

    result["reason"] = f"Profit rate {profit_rate:.2f}% is below threshold {threshold_rate:.2f}%."
    return result
