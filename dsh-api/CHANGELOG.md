# Changelog

All notable changes to `dsh-api` are documented here. This project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `id:` line on every SSE broadcast frame; `ready` frame now reports
  `nextEventId` and echoes any client-supplied `Last-Event-ID`. The
  stream stays ephemeral — nothing is replayed — but sequence numbers
  are visible for gap detection and observability.
- Runnable examples under `examples/`: `curl.sh` (every endpoint,
  read-only + optional `--write` mode) and `events.mjs` (dependency-free
  Node subscriber for `/dsh-api/events`).
- `.editorconfig` and `.gitattributes` to normalise line endings and
  indentation across contributors.
- GitHub Actions CI: `node --check` on every `.mjs` and a
  `package.json → dsh.bundle.patch` shape gate.
- README Troubleshooting section covering the four common failure
  modes (missing bundle, missing service, no companion, idle-killing
  proxy).

### Changed
- `POST /dsh-api/workspace/create` now rejects relative paths and
  captions longer than 200 characters up front with a 400, and maps
  registry errors to more specific status codes (`409` on duplicate,
  `404` on missing target) instead of a blanket 400.
- Expanded `.gitignore` to cover pnpm/yarn logs, common editor caches,
  and local `.env` files.

## [0.1.0] — 2026-08-19

### Added
- Initial release. HTTP control plane under `/dsh-api`:
  - `GET  /dsh-api/health`
  - `GET  /dsh-api/language`, `POST /dsh-api/language`
  - `GET  /dsh-api/workspace/{list,current}`
  - `POST /dsh-api/workspace/create`
  - `GET  /dsh-api/events`  (SSE: `agent-idle`, `approval-needed`,
    `heartbeat`, `server-stopping`, `ready`)
  - Companion-bridged routes: `POST /dsh-api/workspace/open`,
    `/dsh-api/input/paste`, `/dsh-api/window/{show,reload}`,
    `/dsh-api/app/quit`; `GET /dsh-api/companion/state`
- Ships as a standard dsh profile bundle
  (`package.json` → `dsh.bundle.patch = ./cordis.patch.yml`), so
  `dsh plugin --profile web add dsh-api` and
  `dsh plugin --profile web add github:lilming123/dsh-api`
  both work.
- MIT License.

[Unreleased]: https://github.com/lilming123/dsh-api/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/lilming123/dsh-api/releases/tag/v0.1.0
