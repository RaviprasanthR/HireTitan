// HireTitan's thin runner over the pinned career-ops job-board providers.
//
// `scan.mjs --json` prints only a receipt (counts and URLs) and keeps the jobs in career-ops' own
// pipeline and history files, so it cannot return postings. The providers themselves can: each
// takes a board entry and returns plain job objects over public job-board APIs. This runner calls
// them directly: no filters, no history file, no writes.
//
//   stdin : {"boards": [{"company_id", "provider", "careers_url", "max_pages"?, "amazon"?}]}
//   stdout: {"results": [{"company_id", "ok": true, "postings": [...]}
//                       | {"company_id", "ok": false, "error": "..."}]}
//
// CAREER_OPS_DIR points at the pinned career-ops checkout. One board failing never stops the rest.

import path from 'node:path';
import { pathToFileURL } from 'node:url';

// Only these providers are ever run (research R2). Keka is left out until its robots.txt is checked.
const ENABLED = new Set([
  'greenhouse',
  'lever',
  'ashby',
  'workday',
  'smartrecruiters',
  'recruitee',
  'zoho-recruit',
  'amazon',
]);
const PER_BOARD_TIMEOUT_MS = Number(process.env.HIRETITAN_BOARD_TIMEOUT_MS || 90_000);

const root = process.env.CAREER_OPS_DIR;
if (!root) {
  console.error('CAREER_OPS_DIR is not set');
  process.exit(64);
}
const load = (file) => import(pathToFileURL(path.join(root, file)).href);
const { loadProviders } = await load('providers/_registry.mjs');
const { makeHttpCtx } = await load('providers/_http.mjs');
const providers = await loadProviders(path.join(root, 'providers'));

// Provider chatter goes to stderr so stdout stays one JSON document.
console.log = console.error.bind(console);

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString('utf8');
}

function withTimeout(promise, ms) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`The board did not answer within ${ms / 1000} s.`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function posting(job) {
  return {
    title: String(job.title ?? ''),
    url: String(job.url ?? ''),
    location: job.location ? String(job.location) : null,
    description: job.description ? String(job.description) : null,
    posted_at: Number.isFinite(job.postedAt) ? job.postedAt : null,
    requisition_id: job.requisitionId ? String(job.requisitionId) : job.externalId ? String(job.externalId) : null,
  };
}

async function scan(board) {
  if (!ENABLED.has(board.provider)) {
    return { company_id: board.company_id, ok: false, error: `Provider ${board.provider} is not enabled.` };
  }
  const provider = providers.get(board.provider);
  if (!provider) {
    return { company_id: board.company_id, ok: false, error: `Provider ${board.provider} is not installed.` };
  }
  const entry = {
    name: 'board',
    provider: board.provider,
    careers_url: board.careers_url,
    ...(board.max_pages ? { max_pages: board.max_pages } : {}),
    ...(board.amazon ? { amazon: board.amazon } : {}),
  };
  try {
    const jobs = await withTimeout(provider.fetch(entry, makeHttpCtx()), PER_BOARD_TIMEOUT_MS);
    return { company_id: board.company_id, ok: true, postings: jobs.map(posting) };
  } catch (error) {
    return { company_id: board.company_id, ok: false, error: String(error?.message ?? error).slice(0, 300) };
  }
}

const request = JSON.parse(await readStdin());
// A few boards at a time: a batch then lasts about as long as its slowest board, not the sum.
const CONCURRENCY = 4;
const boards = request.boards ?? [];
const results = new Array(boards.length);
let next = 0;
async function worker() {
  while (next < boards.length) {
    const index = next++;
    results[index] = await scan(boards[index]);
  }
}
await Promise.all(Array.from({ length: Math.min(CONCURRENCY, boards.length) }, worker));
process.stdout.write(JSON.stringify({ results }));
// A provider can leave sockets open; the answer is complete, so end now.
process.exit(0);
