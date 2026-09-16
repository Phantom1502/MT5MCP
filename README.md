# MT5 MCP

MetaTrader 5 MCP server.

## Setup

```powershell
cd E:\Projects\MT5MCP
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

## Run

```powershell
python -m server.mt5_server
```

## MT5 portable configuration

Open the same terminal executable in portable mode and log in there. The server reads
the terminal path from `MT5_TERMINAL_PATH` and connects with `portable=True`.

```powershell
$env:MT5_TERMINAL_PATH = "E:\Exness\terminal64.exe"
```

Start the terminal in portable mode, then log in to the account before starting DSH.

## Per-symbol trading configuration

`ask_for_open` and `ask_for_tp` only accept symbols explicitly configured on the
server. The client cannot provide or override thresholds, risk, volume, SL, or TP
settings.

Edit `SYMBOL_TRADE_CONFIG` in `server/config.py`. Each symbol gets its own
configuration:

```text
SYMBOL_TRADE_CONFIG = {
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
}
```

An omitted symbol configuration means trading is disabled for that symbol.
Market-data tools remain read-only and can still query other symbols.

## MCP tools

Trading tools:

- `ask_for_open(symbol, side)`
- `ask_for_tp(symbol)`

Read-only market-data tools:

- `get_symbol_price(symbol)` returns the current bid, ask, last price, and timestamp.
- `get_symbol_candles(symbol, timeframe, window=100)` returns broker candles. Supported
	timeframes are `M1`, `M5`, `M15`, `M30`, `H1`, `H4`, `D1`, `W1`, and `MN1`; `window`
	accepts 1 to 2000 candles.
- `get_symbol_info(symbol)` returns spread in points, digits, lot limits, swaps, and
	contract size.
- `get_market_news(limit=30, window_hours=24)` returns structured macroeconomic events
	from the Forex Factory economic-calendar RSS feed, including country, impact, date,
	forecast, previous, and source link. The RSS URL can be overridden with
	`MT5_NEWS_RSS_URL`.
- `get_external_price(symbol="DXY")` returns an external snapshot for instruments not
	offered by the broker. `DXY` is mapped to Yahoo Finance symbol `DX-Y.NYB` and includes
	price, previous close, change, currency, exchange, and timestamp. This tool is
	read-only and must not be used as the execution price for MT5 orders.

For a morning analysis, call `get_market_news` first, then query symbol info, candles,
and price. News is informational only; trade execution remains restricted to the two
server-side decision tools.

## Important

- MT5 terminal must be running locally.
- You must log in to the account first.
- This is a local native MT5 integration, not a cloud API.
