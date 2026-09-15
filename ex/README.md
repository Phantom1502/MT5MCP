# MT5 scheduler EA

`DemoEA.mq5` keeps the MA filter and trailing logic, but does not open or close trades directly.

## Flow

- `OnTimer` requests one `morning_context` analysis per symbol/magic/date.
- On a new analysis-timeframe bar, MA thresholds request `ltf_trigger` with `intent=open` or `intent=tp`.
- `TrailPositions` remains local and only modifies positions matching `InpMagic` and `_Symbol`.
- `PositionManager.mqh` is not used by this EA.

## Setup

1. Compile `DemoEA.mq5` in MetaEditor.
2. In MT5, open `Tools > Options > Expert Advisors`.
3. Enable `Allow WebRequest for listed URL`.
4. Add:

```text
http://127.0.0.1:3080
```

5. Set `InpDshSessionId` to the target DSH session ID.
6. Keep DeepSeek Harness running with the local `dsh-api` plugin loaded.

The EA expects the local endpoint:

```text
POST http://127.0.0.1:3080/dsh-api/session/analyze
```

The EA only activates analysis. DSH decides whether to call `ask_for_open` or `ask_for_tp`.
