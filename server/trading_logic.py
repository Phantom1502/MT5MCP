from __future__ import annotations

from typing import Any, Literal

from server.config import DEFAULT_TRADE_CONFIG, get_trade_config


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_position_side(position: Any) -> str:
    if getattr(position, "type", 0) in (0, 1):
        return "buy" if getattr(position, "type", 0) == 0 else "sell"
    return "buy" if str(getattr(position, "type", "")).lower() in {"buy", "0"} else "sell"


def _filter_same_side(positions: list[Any], side: Literal["buy", "sell"]) -> list[Any]:
    return [pos for pos in positions if _get_position_side(pos) == side]


def compute_equilibrium_with_add(
    positions: list[Any],
    side: Literal["buy", "sell"],
    add_volume: float,
    add_price: float,
) -> float:
    """Port of EstimateEquilibriumWithAdd: breakeven of same-side group if the new lot were added."""
    group = _filter_same_side(positions, side)
    sum_vol_price = add_volume * add_price
    sum_vol = add_volume
    for pos in group:
        volume = _safe_float(getattr(pos, "volume", 0.0), 0.0)
        entry = _safe_float(getattr(pos, "price_open", add_price), add_price)
        sum_vol_price += volume * entry
        sum_vol += volume
    if sum_vol <= 0:
        return add_price
    return sum_vol_price / sum_vol


def calculate_lot_size(
    entry: float,
    sl: float,
    risk_amount: float,
    tick_value: float,
    tick_size: float,
    lot_step: float,
    min_lot: float,
    max_lot: float,
) -> float:
    """Port of CalculateLotSize (margin-cap step intentionally NOT ported here — needs live
    MT5 order_calc_margin/free_margin, see note below)."""
    sl_dist = abs(entry - sl)
    if sl_dist <= 0 or tick_size <= 0 or lot_step <= 0:
        return 0.0

    lot_size = risk_amount / (sl_dist * (tick_value / tick_size))
    lot_size = (lot_size // lot_step) * lot_step

    if lot_size < min_lot:
        return 0.0
    return min(lot_size, max_lot)


def calc_fibo_lot_size(
    symbol_config: dict[str, Any],
    positions: list[Any],
    side: Literal["buy", "sell"],
    entry: float,
    risk_amount: float,
    point: float,
    tick_value: float,
    tick_size: float,
    lot_step: float,
    min_lot: float,
    max_lot: float,
) -> float:
    """Port of CalFiboLotSize. cnt<2: risk-based sizing off a fixed SL distance.
    cnt>=2: martingale — sum of the two most recently opened same-side volumes, unclamped."""
    group = _filter_same_side(positions, side)
    if len(group) < 2:
        sl_points = symbol_config["buy_sl_points"] if side == "buy" else symbol_config["sell_sl_points"]
        sl_distance = sl_points * point
        sl = entry - sl_distance if side == "buy" else entry + sl_distance
        return calculate_lot_size(entry, sl, risk_amount, tick_value, tick_size, lot_step, min_lot, max_lot)

    sorted_group = sorted(group, key=lambda p: getattr(p, "time", 0), reverse=True)
    vol0 = _safe_float(getattr(sorted_group[0], "volume", 0.0), 0.0)
    vol1 = _safe_float(getattr(sorted_group[1], "volume", 0.0), 0.0)
    return vol0 + vol1


def evaluate_open_signal(
    symbol: str,
    current_price: float,
    positions: list[Any],
    side: Literal["buy", "sell"],
    point: float,
    tick_value: float,
    tick_size: float,
    lot_step: float,
    min_lot: float,
    max_lot: float,
    threshold: float | None = None,
    account_balance: float = 1000.0,
    risk_percent: float | None = None,
) -> dict[str, Any]:
    """Port of OpenOrder. cnt==0: open directly, fixed-distance SL.
    cnt>=1: martingale/risk sizing via CalFiboLotSize, then breakeven-with-add gate."""
    config = get_trade_config(symbol) or DEFAULT_TRADE_CONFIG
    if threshold is None:
        threshold = config["buy_threshold_points"] if side == "buy" else config["sell_threshold_points"]
    if risk_percent is None:
        risk_percent = config["risk_percent"]

    risk_amount = account_balance * risk_percent / 100.0
    group = _filter_same_side(positions, side)
    cnt = len(group)

    lot_size = calc_fibo_lot_size(
        config, positions, side, current_price, risk_amount,
        point, tick_value, tick_size, lot_step, min_lot, max_lot,
    )

    result: dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "threshold": threshold,
        "allowed": False,
        "reason": "",
        "volume": 0.0,
        "entry_price": current_price,
        "stop_loss": current_price,
    }

    if lot_size <= 0:
        result["reason"] = "Computed lot size is zero (below min lot or invalid SL distance)."
        return result

    if cnt == 0:
        sl_points = config["buy_sl_points"] if side == "buy" else config["sell_sl_points"]
        sl_distance = sl_points * point
        sl = current_price - sl_distance if side == "buy" else current_price + sl_distance
        result.update({
            "allowed": True,
            "reason": "No existing same-side position; opened directly.",
            "volume": lot_size,
            "stop_loss": sl,
        })
        return result

    new_eq = compute_equilibrium_with_add(positions, side, lot_size, current_price)
    if side == "buy":
        allowed = current_price > new_eq + threshold
    else:
        allowed = current_price < new_eq - threshold

    if not allowed:
        result["reason"] = f"Price {current_price} not past breakeven-with-add {new_eq} by threshold {threshold}."
        return result

    result.update({
        "allowed": True,
        "reason": "Breakeven-with-add gate passed; SL moved to new equilibrium.",
        "volume": lot_size,
        "stop_loss": new_eq,
    })
    return result


def evaluate_tp_signal(
    position: Any,
    current_price: float,
    account_balance: float = 1000.0,
    threshold_rate: float | None = None,
) -> dict[str, Any]:
    config = get_trade_config(getattr(position, "symbol", "")) or DEFAULT_TRADE_CONFIG
    threshold_rate = config["tp_profit_rate_percent"] if threshold_rate is None else threshold_rate

    position_type = _get_position_side(position)
    entry = _safe_float(getattr(position, "price_open", current_price), current_price)
    volume = _safe_float(getattr(position, "volume", 0.0), 0.0)
    current_profit = (current_price - entry) * volume if position_type == "buy" else (entry - current_price) * volume

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