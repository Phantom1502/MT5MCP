// events.mjs — subscribe to /dsh-api/events with Node's built-in fetch.
//
// Usage:
//   node examples/events.mjs                    # default port 3080
//   PORT=3181 node examples/events.mjs          # against `dsh web --port 3181`
//
// The stream never terminates on its own; press Ctrl-C to stop. Each frame
// is printed as one line: `<event-name> <json-payload>`. Errors interrupt
// the run — a production consumer should reconnect with exponential
// back-off (see dsh-desktop's src/apiClient.js for a reference impl).

const port = process.env.PORT || '3080';
const url = `http://127.0.0.1:${port}/dsh-api/events`;

const res = await fetch(url, { headers: { accept: 'text/event-stream' } });
if (!res.ok || !res.body) {
  console.error(`SSE handshake failed: ${res.status}`);
  process.exit(1);
}
console.error(`connected: ${url}`);

// Very small SSE frame accumulator — enough for /dsh-api/events, which
// only uses `event:` + `data:` lines. Fields are separated by blank lines.
let buf = '';
const decoder = new TextDecoder();
for await (const chunk of res.body) {
  buf += decoder.decode(chunk, { stream: true });
  let sep;
  while ((sep = buf.indexOf('\n\n')) !== -1) {
    const frame = buf.slice(0, sep);
    buf = buf.slice(sep + 2);
    let event = 'message';
    let data = '';
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data += (data ? '\n' : '') + line.slice(5).trim();
      // `retry:`, `id:` and comments (`:...`) are ignored for this demo.
    }
    if (data) console.log(event, data);
  }
}
