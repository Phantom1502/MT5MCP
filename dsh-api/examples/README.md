# examples

Runnable snippets against a local `dsh-api`. Point them at whatever
port your dsh is listening on (default `3080`).

## `curl.sh`

Exercise every read endpoint, and — with `--write` — the two POST
routes as well. Requires `curl` and (optionally) `jq` for pretty
printing.

```sh
./examples/curl.sh                 # read-only
PORT=3181 ./examples/curl.sh       # against dsh web --port 3181
./examples/curl.sh --write         # also POST /language and /workspace/create
```

## `events.mjs`

A dependency-free Node subscriber for `/dsh-api/events`. Uses Node 18+'s
built-in `fetch` and streams the SSE body; each frame prints as
`<event> <json>` on stdout. Handy for verifying the plugin is loaded
and events are flowing.

```sh
node examples/events.mjs
PORT=3181 node examples/events.mjs
```

Ctrl-C to stop. For a production-grade consumer with reconnection and
idle-timeout handling, see the reference implementation in
[`dsh-desktop`](https://github.com/lilming123/dsh-desktop)'s
`src/apiClient.js`.
