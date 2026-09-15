from __future__ import annotations

import logging
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any

import MetaTrader5 as mt5
from mcp.server import MCPServer
from pydantic import BaseModel, Field

from server.config import get_trade_config
from server.trading_logic import _get_position_side, _safe_float, evaluate_open_signal, evaluate_tp_signal

mcp = MCPServer("mt5")
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s mt5mcp %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mt5mcp")
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler("mt5mcp.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s mt5mcp %(message)s"))
logger.addHandler(file_handler)


def report_tool_errors(function: Any) -> Any:
    """Keep tool failures visible to MCP clients instead of returning a generic error."""
    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return function(*args, **kwargs)
        except Exception as error:
            mt5_error = mt5.last_error()
            logger.exception("Tool failed: %s error=%s", function.__name__, mt5_error)
            return {
                "ok": False,
                "error": str(error),
                "mt5_error": str(mt5_error),
                "tool": function.__name__,
            }

    return wrapped


class AccountInfo(BaseModel):
    login: int = Field(description="MT5 account login")
    balance: float = Field(description="Account balance")
    equity: float = Field(description="Account equity")
    margin: float = Field(description="Used margin")
    currency: str = Field(description="Account currency")
    leverage: int = Field(description="Leverage")


class SymbolQuote(BaseModel):
    symbol: str = Field(description="Trading symbol")
    bid: float = Field(description="Bid price")
    ask: float = Field(description="Ask price")
    last: float = Field(description="Last price")
    time: int = Field(description="Quote timestamp in seconds")


TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}
DEFAULT_NEWS_RSS_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
EXTERNAL_SYMBOL_MAP = {
    "DXY": "DX-Y.NYB",
}


def ensure_mt5_connected() -> None:
    terminal_path = os.getenv("MT5_TERMINAL_PATH", r"E:\Exness\terminal64.exe")
    logger.info("MT5 portable initialize starting: path=%s", terminal_path)
    if not mt5.initialize(path=terminal_path, portable=True):
        error = mt5.last_error()
        logger.error("MT5 initialize failed: %s", error)
        raise RuntimeError(f"MT5 initialize failed: {error}")
    logger.debug("MT5 connection initialized")


def ensure_symbol_selected(symbol: str) -> None:
    """Make the symbol available in MT5 Market Watch before using it."""
    logger.info("Selecting symbol: symbol=%s", symbol)
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        error = mt5.last_error()
        logger.error("Symbol not found: symbol=%s error=%s", symbol, error)
        raise RuntimeError(f"Symbol {symbol} was not found in MT5: {error}")
    if not mt5.symbol_select(symbol, True):
        error = mt5.last_error()
        logger.error("Failed to select symbol: symbol=%s error=%s", symbol, error)
        raise RuntimeError(f"Failed to select symbol {symbol} in MT5: {error}")
    logger.info("Symbol selected: symbol=%s point=%s", symbol, symbol_info.point)


def _xml_text(element: ET.Element, name: str) -> str | None:
    value = element.findtext(name)
    return value.strip() if value and value.strip() else None


@mcp.tool()
@report_tool_errors
def get_market_news(
    limit: int = 30,
    window_hours: int = 24,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Get recent and upcoming high-value macro events from the economic calendar RSS feed."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if not 1 <= window_hours <= 168:
        raise ValueError("window_hours must be between 1 and 168")

    rss_url = os.getenv("MT5_NEWS_RSS_URL", DEFAULT_NEWS_RSS_URL)
    logger.info("get_market_news called: limit=%s window_hours=%s source=%s", limit, window_hours, rss_url)
    request = urllib.request.Request(
        rss_url,
        headers={"User-Agent": "MT5MCP/0.1 market-news-reader"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read(2_000_000)
    except Exception as error:
        raise RuntimeError(f"Failed to fetch market news RSS: {error}") from error

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise RuntimeError(f"Market news RSS returned invalid XML: {error}") from error

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    events = []
    for item in root.findall(".//event") + root.findall(".//item"):
        title = _xml_text(item, "title") or _xml_text(item, "event")
        if not title:
            continue
        event = {
            "title": title,
            "country": _xml_text(item, "country"),
            "impact": _xml_text(item, "impact") or _xml_text(item, "impactTitle"),
            "date": _xml_text(item, "date"),
            "time": _xml_text(item, "time"),
            "forecast": _xml_text(item, "forecast"),
            "previous": _xml_text(item, "previous"),
            "published_at": _xml_text(item, "pubDate") or _xml_text(item, "published"),
            "summary": _xml_text(item, "description") or _xml_text(item, "summary"),
            "link": _xml_text(item, "link"),
            "source": rss_url,
        }
        published_at = event["published_at"]
        if published_at:
            try:
                parsed_time = datetime.strptime(published_at, "%a, %d %b %Y %H:%M:%S %z")
                if parsed_time < cutoff:
                    continue
            except ValueError:
                logger.warning("Could not parse news timestamp: %s", published_at)
        events.append(event)
        if len(events) >= limit:
            break

    logger.info("get_market_news completed: count=%s source=%s", len(events), rss_url)
    return events


@mcp.tool()
@report_tool_errors
def get_external_price(symbol: str = "DXY") -> dict[str, Any]:
    """Get an external market snapshot for instruments unavailable in the broker terminal."""
    normalized_symbol = symbol.upper()
    yahoo_symbol = EXTERNAL_SYMBOL_MAP.get(normalized_symbol, symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(yahoo_symbol)}?range=1d&interval=1m"
    logger.info("get_external_price called: symbol=%s yahoo_symbol=%s", normalized_symbol, yahoo_symbol)
    request = urllib.request.Request(url, headers={"User-Agent": "MT5MCP/0.1 external-price-reader"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read(2_000_000))
    except Exception as error:
        raise RuntimeError(f"Failed to fetch external price for {normalized_symbol}: {error}") from error

    result = payload.get("chart", {}).get("result")
    if not result:
        detail = payload.get("chart", {}).get("error")
        raise RuntimeError(f"External source returned no data for {normalized_symbol}: {detail}")

    metadata = result[0].get("meta", {})
    price = metadata.get("regularMarketPrice")
    previous_close = metadata.get("previousClose") or metadata.get("chartPreviousClose")
    if price is None:
        raise RuntimeError(f"External source returned no current price for {normalized_symbol}")

    change = float(price) - float(previous_close) if previous_close is not None else None
    change_percent = (change / float(previous_close) * 100.0) if change is not None and previous_close else None
    return {
        "symbol": normalized_symbol,
        "source_symbol": yahoo_symbol,
        "price": float(price),
        "previous_close": float(previous_close) if previous_close is not None else None,
        "change": change,
        "change_percent": change_percent,
        "currency": metadata.get("currency"),
        "exchange": metadata.get("exchangeName"),
        "timestamp": int(metadata["regularMarketTime"]) if metadata.get("regularMarketTime") else None,
        "source": "Yahoo Finance Chart API",
    }


@mcp.tool()
@report_tool_errors
def get_symbol_price(symbol: str) -> dict[str, Any]:
    """Get the latest broker price snapshot for a symbol."""
    logger.info("get_symbol_price called: symbol=%s", symbol)
    ensure_mt5_connected()
    ensure_symbol_selected(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        error = mt5.last_error()
        raise RuntimeError(f"Failed to get price for {symbol}: {error}")
    return {
        "symbol": symbol,
        "bid": float(tick.bid),
        "ask": float(tick.ask),
        "last": float(tick.last),
        "timestamp": int(tick.time),
    }


@mcp.tool()
@report_tool_errors
def get_symbol_candles(
    symbol: str,
    timeframe: str,
    window: int = 100,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Get recent broker candles for a symbol and timeframe."""
    normalized_timeframe = timeframe.upper()
    if normalized_timeframe not in TIMEFRAME_MAP:
        supported = ", ".join(TIMEFRAME_MAP)
        raise ValueError(f"Unsupported timeframe {timeframe!r}. Use one of: {supported}")
    if not 1 <= window <= 2000:
        raise ValueError("window must be between 1 and 2000")

    logger.info(
        "get_symbol_candles called: symbol=%s timeframe=%s window=%s",
        symbol,
        normalized_timeframe,
        window,
    )
    ensure_mt5_connected()
    ensure_symbol_selected(symbol)
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME_MAP[normalized_timeframe], 0, window)
    if rates is None:
        error = mt5.last_error()
        raise RuntimeError(f"Failed to get candles for {symbol}: {error}")

    return [
        {
            "time": int(rate["time"]),
            "open": float(rate["open"]),
            "high": float(rate["high"]),
            "low": float(rate["low"]),
            "close": float(rate["close"]),
            "tick_volume": int(rate["tick_volume"]),
        }
        for rate in rates
    ]


@mcp.tool()
@report_tool_errors
def get_symbol_info(symbol: str) -> dict[str, Any]:
    """Get broker trading specifications and current spread for a symbol."""
    logger.info("get_symbol_info called: symbol=%s", symbol)
    ensure_mt5_connected()
    ensure_symbol_selected(symbol)
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if info is None or tick is None:
        error = mt5.last_error()
        raise RuntimeError(f"Failed to get symbol information for {symbol}: {error}")

    point = float(info.point)
    spread = (float(tick.ask) - float(tick.bid)) / point if point > 0 else 0.0
    return {
        "symbol": symbol,
        "spread": spread,
        "digits": int(info.digits),
        "min_lot": float(info.volume_min),
        "max_lot": float(info.volume_max),
        "swap_long": float(info.swap_long),
        "swap_short": float(info.swap_short),
        "contract_size": float(info.trade_contract_size),
    }


def get_account() -> AccountInfo:
    """Get current MT5 account information."""
    ensure_mt5_connected()
    account = mt5.account_info()
    if account is None:
        raise RuntimeError(f"Failed to get MT5 account info: {mt5.last_error()}")

    return AccountInfo(
        login=int(account.login),
        balance=float(account.balance),
        equity=float(account.equity),
        margin=float(account.margin),
        currency=str(account.currency or ""),
        leverage=int(account.leverage),
    )


def get_symbols() -> list[str]:
    """List visible symbols available in MT5 terminal."""
    ensure_mt5_connected()
    symbols = mt5.symbols_get()
    if symbols is None:
        raise RuntimeError(f"Failed to get symbols: {mt5.last_error()}")
    return [s.name for s in symbols][:50]


def get_quote(symbol: str) -> SymbolQuote:
    """Get the latest quote for a symbol."""
    ensure_mt5_connected()
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"Failed to get tick for {symbol}: {mt5.last_error()}")
    return SymbolQuote(
        symbol=symbol,
        bid=float(tick.bid),
        ask=float(tick.ask),
        last=float(tick.last),
        time=int(tick.time),
    )


@mcp.tool()
@report_tool_errors
def ask_for_open(
    symbol: str,
    side: str,
) -> dict[str, Any]:
    """Check the open condition and execute the trade when it's allowed by the internal MT5 logic."""
    logger.info("ask_for_open called: symbol=%s side=%s", symbol, side)
    try:
        ensure_mt5_connected()
        ensure_symbol_selected(symbol)
        account = mt5.account_info()
        if account is None:
            raise RuntimeError(f"Failed to get MT5 account info: {mt5.last_error()}")
        account_balance = max(float(account.balance), 1.0)
        side = side.lower()
        if side not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")
    except Exception:
        logger.exception("ask_for_open failed during connection or input validation: symbol=%s side=%s", symbol, side)
        raise

    current = mt5.symbol_info_tick(symbol)
    if current is None:
        error = mt5.last_error()
        logger.error("No tick for symbol=%s: %s", symbol, error)
        raise RuntimeError(f"Failed to get tick for {symbol}: {error}")

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        logger.error("Symbol is unavailable: symbol=%s mt5_error=%s", symbol, mt5.last_error())
        raise RuntimeError(f"Symbol {symbol} is not available in the MT5 terminal.")

    config = get_trade_config()
    point_size = float(symbol_info.point)
    threshold_points = config["buy_threshold_points"] if side == "buy" else config["sell_threshold_points"]
    threshold_price = threshold_points * point_size

    positions = mt5.positions_get(symbol=symbol) or []
    current_price = float(current.bid if side == "buy" else current.ask)
    decision = evaluate_open_signal(
        symbol=symbol,
        current_price=current_price,
        positions=positions,
        side=side,
        threshold=threshold_price,
        account_balance=account_balance,
    )
    logger.info("ask_for_open decision: symbol=%s side=%s decision=%s", symbol, side, decision)

    if not decision["allowed"]:
        return decision

    sl_points = config["buy_sl_points"] if side == "buy" else config["sell_sl_points"]
    sl_distance = sl_points * point_size
    sl = current_price - sl_distance if side == "buy" else current_price + sl_distance
    tp_distance = max((current_price - sl) * config["tp_multiplier"], 0.0) if side == "buy" else max((sl - current_price) * config["tp_multiplier"], 0.0)
    tp = current_price + tp_distance if side == "buy" else current_price - tp_distance

    request = {
        "action": mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL,
        "symbol": symbol,
        "volume": float(decision["volume"]),
        "type": mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL,
        "price": current_price,
        "sl": float(sl),
        "tp": float(tp),
        "comment": "ask_for_open",
        "type_filling": mt5.ORDER_FILLING_FOK,
    }

    order_check = mt5.order_check(request)
    if not order_check or order_check.get("retcode") != mt5.TRADE_RETCODE_DONE:
        logger.error("MT5 order_check rejected: symbol=%s side=%s request=%s result=%s error=%s", symbol, side, request, order_check, mt5.last_error())
        decision["allowed"] = False
        decision["reason"] = f"MT5 order validation failed: {order_check}"
        return decision

    order_result = mt5.order_send(request)
    if order_result is None:
        logger.error("MT5 order_send returned None: symbol=%s side=%s error=%s", symbol, side, mt5.last_error())
        decision["allowed"] = False
        decision["reason"] = f"MT5 order_send failed: {mt5.last_error()}"
        return decision

    decision["order_ticket"] = int(order_result.order)
    decision["order_result"] = str(order_result.comment)
    decision["entry_price"] = float(order_result.price)
    decision["stop_loss"] = float(order_result.sl if order_result.sl else sl)
    decision["take_profit"] = float(order_result.tp if order_result.tp else tp)
    decision["reason"] = "Order executed successfully by MT5."
    logger.info("ask_for_open completed: symbol=%s side=%s ticket=%s", symbol, side, order_result.order)
    return decision


@mcp.tool()
@report_tool_errors
def ask_for_tp(symbol: str) -> dict[str, Any]:
    """Check whether the current position group for a symbol should be closed.

    Close is allowed only if the realized profit exceeds the configured rate versus balance.
    """

    def close_all_positions_by_type(symbol: str, side: str) -> dict[str, Any]:
        """Close all positions of the same side for the symbol."""
        ensure_mt5_connected()
        positions = mt5.positions_get(symbol=symbol) or []
        matched = [pos for pos in positions if _get_position_side(pos) == side.lower()]
        closed = []

        for pos in matched:
            ticket = int(getattr(pos, "ticket", 0))
            if ticket <= 0:
                logger.error("Cannot close position with invalid ticket: symbol=%s side=%s position=%s", symbol, side, pos)
                continue
            if mt5.position_close(ticket):
                closed.append(ticket)
            else:
                logger.error("Failed to close position: symbol=%s side=%s ticket=%s error=%s", symbol, side, ticket, mt5.last_error())

        return {
            "symbol": symbol,
            "side": side.lower(),
            "closed_ticket_count": len(closed),
            "closed_tickets": closed,
            "reason": "Positions closed successfully." if closed else "No positions matched the requested side.",
        }

    logger.info("ask_for_tp called: symbol=%s", symbol)
    ensure_mt5_connected()
    ensure_symbol_selected(symbol)
    account = mt5.account_info()
    if account is None:
        logger.error("Failed to read MT5 account for TP: symbol=%s error=%s", symbol, mt5.last_error())
        raise RuntimeError(f"Failed to get MT5 account info: {mt5.last_error()}")
    account_balance = max(float(account.balance), 1.0)
    current = mt5.symbol_info_tick(symbol)
    if current is None:
        logger.error("No tick for TP: symbol=%s error=%s", symbol, mt5.last_error())
        raise RuntimeError(f"Failed to get tick for {symbol}: {mt5.last_error()}")

    positions = mt5.positions_get(symbol=symbol) or []
    logger.info("ask_for_tp positions: symbol=%s count=%d", symbol, len(positions))
    if not positions:
        return {"symbol": symbol, "allowed": False, "reason": "No position found for symbol."}

    side_positions = positions
    current_price = float(current.bid if getattr(side_positions[0], "type", 0) == 0 else current.ask)
    result = {
        "symbol": symbol,
        "allowed": False,
        "profit": 0.0,
        "profit_rate_percent": 0.0,
        "threshold_rate_percent": get_trade_config()["tp_profit_rate_percent"],
        "reason": "",
    }

    group_profit = 0.0
    for pos in side_positions:
        entry = _safe_float(getattr(pos, "price_open", current_price), current_price)
        volume = _safe_float(getattr(pos, "volume", 0.0), 0.0)
        pos_type = _get_position_side(pos)
        if pos_type == "buy":
            group_profit += (current_price - entry) * volume
        else:
            group_profit += (entry - current_price) * volume

    balance = max(account_balance, 1.0)
    profit_rate = (group_profit / balance) * 100.0
    threshold = get_trade_config()["tp_profit_rate_percent"]
    result["profit"] = group_profit
    result["profit_rate_percent"] = profit_rate
    result["threshold_rate_percent"] = threshold
    logger.info(
        "ask_for_tp decision: symbol=%s profit=%s profit_rate=%s threshold=%s",
        symbol,
        group_profit,
        profit_rate,
        threshold,
    )

    if group_profit <= 0:
        result["reason"] = "Group has not made profit yet."
        return result
    if profit_rate >= threshold:
        close_side = _get_position_side(side_positions[0])
        close_result = close_all_positions_by_type(symbol, close_side)
        result["allowed"] = True
        result["reason"] = f"Group profit rate {profit_rate:.2f}% is above threshold {threshold:.2f}%."
        result["close_result"] = close_result
        logger.info("ask_for_tp close result: symbol=%s side=%s result=%s", symbol, close_side, close_result)
        return result

    result["reason"] = f"Group profit rate {profit_rate:.2f}% is below threshold {threshold:.2f}%."
    return result


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
