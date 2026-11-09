// Test helper: log every HTTP request the career-ops providers make (constitution VII).
//
// Loaded with `node --require request_probe.cjs runner.mjs`, so it runs before any ESM import and
// can wrap both the global `fetch` and undici's `fetch`, the two ways the pinned providers send
// requests. One JSON line per request ({"method", "url"}) goes to HIRETITAN_PROBE_LOG.
//
//   HIRETITAN_PROBE_MODE=replay (default): answer every request with 200 {} and touch no network.
//   HIRETITAN_PROBE_MODE=live            : pass the request through (used only to record a trace).

const fs = require('node:fs');

const logPath = process.env.HIRETITAN_PROBE_LOG;
const live = process.env.HIRETITAN_PROBE_MODE === 'live';
if (!logPath) throw new Error('HIRETITAN_PROBE_LOG is not set');

function wrap(original) {
  return async function probedFetch(input, init) {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = String((init && init.method) || (typeof input === 'object' && input.method) || 'GET').toUpperCase();
    fs.appendFileSync(logPath, JSON.stringify({ method, url }) + '\n');
    if (live) return original(input, init);
    return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } });
  };
}

globalThis.fetch = wrap(globalThis.fetch);

// undici's own fetch, used by the providers' connection guard. CommonJS exports can be replaced
// before the ESM providers link against them.
try {
  const undiciPath = require.resolve('undici', { paths: [process.env.CAREER_OPS_DIR || process.cwd()] });
  const undici = require(undiciPath);
  undici.fetch = wrap(undici.fetch);
} catch {
  // undici is optional for some providers; global fetch is wrapped either way
}
