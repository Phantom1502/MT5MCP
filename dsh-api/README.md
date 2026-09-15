# dsh-api — HTTP control-plane plugin for DeepSeek Harness

[![ci](https://github.com/lilming123/dsh-api/actions/workflows/ci.yml/badge.svg)](https://github.com/lilming123/dsh-api/actions/workflows/ci.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)

`dsh-api` is a first-party plugin for [DeepSeek Harness (dsh)][dsh] that
exposes dsh's own internal capabilities on the loopback HTTP socket dsh is
already listening on. Any process on the same machine — a desktop wrapper,
a browser extension, a CLI, an editor integration — can drive dsh through
one uniform entry point, instead of reaching into its in-process services
directly.

- Route prefix (default): **`/dsh-api`**
- Binds only where dsh already binds (127.0.0.1)
- Zero runtime dependencies beyond Node itself

[dsh]: https://www.npmjs.com/package/@deepseek-ai/dsh

## Install

```sh
# From GitHub (any dsh profile):
dsh plugin --profile web add github:lilming123/dsh-api

# From npm (once published):
dsh plugin --profile web add dsh-api
```

`dsh plugin` is a thin pnpm wrapper. Both forms drop the package into
`$DSH_HOME/profiles/<profile>/node_modules/` and register `dsh-api` in the
profile's bundle list — the next `dsh web` picks it up automatically, no
`--patch` flag needed.

The desktop app [`dsh-desktop`][dsh-desktop] detects an already-installed
`dsh-api` and skips its bundled fallback; you only need to install this
plugin manually if you drive dsh directly.

[dsh-desktop]: https://github.com/lilming123/dsh-desktop

## Endpoints

Two layers, mounted under the same `/dsh-api` prefix:

### 1. Native (always available once the plugin is loaded)

| Method | Path                        | Purpose                                                 |
| ------ | --------------------------- | ------------------------------------------------------- |
| GET    | `/dsh-api/health`           | Liveness + basic identity (dsh port, cwd, companion?)   |
| GET    | `/dsh-api/language`         | Read `locale.preference`                                |
| POST   | `/dsh-api/language`         | Write `locale.preference` (`{ "language": "zh"\|"en" }`) |
| GET    | `/dsh-api/workspace/list`   | List every workspace known to `workspaceRegistry`       |
| GET    | `/dsh-api/workspace/current`| Current cwd + companion snapshot (if registered)        |
| POST   | `/dsh-api/workspace/create` | `{ path, title? }` — register a new workspace entry     |
| POST   | `/dsh-api/session/analyze`  | Queue an analysis prompt into a live DSH session         |
| GET    | `/dsh-api/events`           | Server-Sent Events stream (see below)                   |

### 2. Companion-bridged (needs a registered companion process)

A "companion" is any local process that writes
`$DSH_HOME/dsh-api-companion.json` with `{ port, token, pid, ... }` and
serves the `/companion/*` protocol. These routes are 503 when no companion
is registered; the native routes above keep working regardless.

| Method | Path                          | Purpose                                            |
| ------ | ----------------------------- | -------------------------------------------------- |
| GET    | `/dsh-api/companion/state`    | Companion state snapshot                           |
| POST   | `/dsh-api/workspace/open`     | Switch dsh cwd (restarts dsh under the companion)  |
| POST   | `/dsh-api/input/paste`        | `{ text }` — inject text into the dsh UI          |
| POST   | `/dsh-api/window/show`        | Focus the host window                              |
| POST   | `/dsh-api/window/reload`      | Reload the host window                             |
| POST   | `/dsh-api/app/quit`           | Quit the host app                                  |

### `/dsh-api/events` (Server-Sent Events)

Long-lived HTTP GET producing named SSE frames:

```
event: ready
data: {"timestamp":1730000000000}

event: agent-idle
data: {"sessionId":"…","title":"…","previousStatus":"running","timestamp":…}

event: approval-needed
data: {"sessionId":"…","kind":"…","summary":"…","timestamp":…}

event: analysis-completed
data: {"requestId":"…","sessionId":"…","jobType":"…","symbol":"…","timestamp":…}

event: heartbeat
data: {"timestamp":…}
```

- `agent-idle` fires when any `agent/status` event transitions `running → idle`.
- `approval-needed` is a **read-only bypass** of dsh's `approval/request`
  waterfall — the plugin observes the request, broadcasts a summary, and
  passes control back to the real answerer chain unchanged.
- `heartbeat` is emitted every 25 seconds so proxies don't idle-kill the
  connection.
- On dsh shutdown, subscribers receive a `server-stopping` event before the
  socket closes.

### Session analysis

`POST /dsh-api/session/analyze` queues a prompt through DSH's native
`sessionController` service. It does not require a companion process and
returns immediately with `202 Accepted`.

```json
{
  "sessionId": "SESSION_ID",
  "requestId": "ltf-20260915-001",
  "jobType": "ltf_trigger",
  "symbol": "XAUUSDc",
  "side": "sell",
  "timeframes": ["M15", "M5"],
  "trigger": "price_reached_equilibrium",
  "contextRef": "morning-20260915"
}
```

Supported job types are `morning_context` and `ltf_trigger`. The caller only
activates analysis; trading thresholds, volume, SL/TP, and the final trade
decision remain inside the MT5 MCP tools.

## Security

- dsh binds `127.0.0.1` only; this plugin reuses that socket.
- Mutating requests validate `Origin`: no `Origin` header (CLI) and
  loopback origins are allowed; anything else is `403`.
- Companion-bridged routes forward the discovery-file token in
  `x-dsh-api-companion-token`; the companion is expected to reject
  mismatches.

## Configuration

The plugin exposes two knobs, both settable in the loader entry's
`config: { ... }`:

| Key            | Default                              | Purpose                                       |
| -------------- | ------------------------------------ | --------------------------------------------- |
| `basePath`     | `/dsh-api`                           | HTTP route prefix                             |
| `companionFile`| `$DSH_HOME/dsh-api-companion.json`   | Companion discovery file to read on demand    |

Example (`$DSH_HOME/profiles/web/cordis.patch.yml`):

```yaml
- id: dsh-api
  config:
    basePath: /control
```

## Development

`dsh-api` is a plain-ESM plugin — no build step. Clone the repo, drop the
file into a dsh profile, and start dsh with `--patch`:

```sh
git clone https://github.com/lilming123/dsh-api.git
cd dsh-api

# One-time: expose to a profile as a live-edit checkout
mkdir -p "$DSH_HOME/profiles/web/dsh-api-dev"
ln -sf "$PWD/index.mjs" "$DSH_HOME/profiles/web/dsh-api-dev/index.mjs"
cat > /tmp/dsh-api-dev.patch.yml <<'YML'
- insert:
    - id: dsh-api-dev
      name: ./dsh-api-dev/index.mjs
YML

dsh web --patch /tmp/dsh-api-dev.patch.yml --port 3181

# In another shell:
curl http://127.0.0.1:3181/dsh-api/health
curl -N http://127.0.0.1:3181/dsh-api/events
```

More runnable snippets live under [`examples/`](./examples): `curl.sh`
walks every endpoint, and `events.mjs` is a dependency-free Node SSE
subscriber.

## Troubleshooting

**`/dsh-api/*` returns 404.** The plugin isn't loaded. Check that
`~/.dsh/profiles/web/package.json` lists `dsh-api` under
`dsh.profile.bundles`, and that `~/.dsh/profiles/web/node_modules/dsh-api`
exists. Re-run `dsh plugin --profile web add dsh-api` if either is
missing.

**`/dsh-api/workspace/create` returns 503.** `workspaceRegistry`
isn't in the current dsh context — either your dsh predates the service
or a profile patch has stripped it. Upgrade dsh (`npm i -g @deepseek-ai/dsh`)
and try again.

**`/dsh-api/*/companion routes return 503.** No companion is
registered. This is expected when you run dsh directly rather than
through a wrapper like [dsh-desktop][dsh-desktop]; the native routes
(`/health`, `/language`, `/workspace/*`, `/events`) work regardless.

**SSE stream disconnects every ~60 seconds.** A reverse proxy is
idle-killing the stream despite our 25-second `heartbeat` frames. Bump
its idle timeout, or drop the proxy — `dsh-api` binds to `127.0.0.1`
and doesn't need one.

[dsh-desktop]: https://github.com/lilming123/dsh-desktop

## License

MIT © 2026 lilming123
