import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const OUT = new URL('../../../../notes/f29/qa/', import.meta.url).pathname;
const FE = 'http://localhost:3000';
const BE = 'http://localhost:8081/api';
const PORT = 9334;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
if (!process.env.T_EMAIL || !process.env.T_PASS) { console.error('thiếu T_EMAIL/T_PASS'); process.exit(2); }
mkdirSync(join(OUT, 'screens'), { recursive: true });

const login = await (await fetch(`${BE}/auth/login`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email: process.env.T_EMAIL, password: process.env.T_PASS }) })).json();
if (!login.token) { console.error('đăng nhập thất bại'); process.exit(2); }
const api = async (path) => (await fetch(`${BE}/seller/analytics${path}`, { headers: { authorization: `Bearer ${login.token}` } })).json();

const profile = mkdtempSync(join(tmpdir(), 'cdp-'));
const chrome = spawn('google-chrome', ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, '--no-first-run', 'about:blank'], { stdio: 'ignore' });
const cleanup = () => { chrome.kill(); try { rmSync(profile, { recursive: true, force: true }); } catch {} };
setTimeout(() => { console.error('quá 15 phút, dừng'); cleanup(); process.exit(2); }, 900000).unref();

let page = 'login'; const errors = []; const http = []; const done = new Set(); const pages = [];
let id = 0; const pending = new Map(); let ws;
const local = (url) => !url || url.startsWith(FE) || url.startsWith('http://localhost:8081');
const send = (method, params = {}) => Promise.race([
  new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); }),
  sleep(30000).then(() => { throw new Error(`CDP ${method} quá 30 s`); }),
]);
const evaluate = async (expr) => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
const text = (expr) => evaluate(`(${expr} || "")`);

async function load(name, path, readyExpr, timeout = 30000) {
  page = name;
  const t0 = Date.now();
  await send('Page.navigate', { url: FE + path });
  while (Date.now() - t0 < timeout) {
    await sleep(25);
    if (await evaluate(`location.pathname === ${JSON.stringify(path)} && (${readyExpr})`)) return { ms: Date.now() - t0, ok: true };
  }
  return { ms: Date.now() - t0, ok: false };
}

async function shot(name) {
  const { result } = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(OUT, 'screens', `${name}.png`), Buffer.from(result.data, 'base64'));
}

function factorMismatches(factors, rows) {
  return factors.flatMap((f) => {
    const off = f.state === 'not_applicable' || f.state === 'technical_failure';
    const want = off ? 'Chưa tính' : `Đạt ${Math.round(Math.min(100, (f.points / f.weight) * 100))}%`;
    const row = rows.find((t) => t.startsWith(f.label));
    return row && row.includes(want) ? [] : [`${f.key}: muốn "${want}", trang "${(row || '').replace(/\s+/g, ' ').slice(0, 80)}"`];
  });
}

try {
  let targetInfo;
  for (let i = 0; i < 50 && !targetInfo; i++) {
    try { targetInfo = (await (await fetch(`http://localhost:${PORT}/json/list`)).json()).find((t) => t.type === 'page'); } catch {}
    await sleep(200);
  }
  ws = new WebSocket(targetInfo.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r));
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); return; }
    const p = m.params || {};
    if (m.method === 'Runtime.exceptionThrown') errors.push({ page, kind: 'exception', text: p.exceptionDetails?.exception?.description || p.exceptionDetails?.text });
    if (m.method === 'Runtime.consoleAPICalled' && p.type === 'error') errors.push({ page, kind: 'console', text: p.args.map((a) => a.value ?? a.description).join(' ').slice(0, 300) });
    if (m.method === 'Log.entryAdded' && p.entry.level === 'error') errors.push({ page: local(p.entry.url) ? page : 'external', kind: 'log', text: `${p.entry.text} ${p.entry.url || ''}`.slice(0, 300) });
    if (m.method === 'Network.responseReceived' && p.response.url.includes('/api/')) {
      done.add(p.response.url);
      if (p.response.status >= 400) http.push({ page, url: p.response.url, status: p.response.status });
    }
  });
  for (const d of ['Page', 'Network', 'Runtime', 'Log']) await send(`${d}.enable`);
  await send('Emulation.setDeviceMetricsOverride', { width: 1366, height: 900, deviceScaleFactor: 1, mobile: false });

  await load('login', '/login', '!!document.querySelector("input[type=password]")');
  await evaluate(`(() => {
    const set = (el, v) => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); };
    set(document.querySelector('input[type=email]'), ${JSON.stringify(process.env.T_EMAIL)});
    set(document.querySelector('input[type=password]'), ${JSON.stringify(process.env.T_PASS)});
    document.querySelector('form button[type=submit]').click();
  })()`);
  for (let i = 0; i < 100 && (await evaluate('location.pathname')) === '/login'; i++) await sleep(100);
  await sleep(2000);

  const list = await load('listings', '/seller/insights/listings', 'document.querySelectorAll(\'a[href*="/seller/insights/listings/"]\').length > 0');
  await sleep(1500); await shot('listings');
  const ids = await evaluate(`[...new Set([...document.querySelectorAll('a[href*="/seller/insights/listings/"]')].map(a => a.getAttribute('href').split(/[?#]/)[0].split('/').pop()))]`) || [];
  pages.push({ name: 'listings', ...list, n_links: ids.length });

  for (const pid of ids) {
    const name = `detail-${pid}`;
    const r = await load(name, `/seller/insights/listings/${pid}`, '/Vì sao \\d+ điểm\\?/.test(document.body.innerText || "")');
    const shown = Number((await evaluate('((document.body.innerText || "").match(/Vì sao (\\d+) điểm\\?/) || [])[1]')) ?? NaN);
    const rows = await evaluate(`[...document.querySelectorAll('li')].map(li => li.innerText).filter(t => /Đạt \\d+%|Chưa tính/.test(t))`) || [];
    await shot(name);
    const health = await api(`/listings/${pid}/health`);
    const factors = factorMismatches(health.data?.factors || [], rows);
    pages.push({ name, ...r, shown, api_score: health.data?.score, match: shown === Math.floor(health.data?.score ?? NaN) && !factors.length, factors });
  }
} catch (e) {
  errors.push({ page, kind: 'script', text: String(e?.message || e) });
} finally {
  cleanup();
}

const inF29 = (x) => x.page !== 'login' && x.page !== 'external';
const f29Errors = errors.filter(inF29);
const f29Http = http.filter(inF29);
const mismatches = pages.filter((p) => p.match === false || p.ok === false).map((p) => p.name);
const report = { n_pages: pages.length, pages, console_errors: f29Errors, outside_f29_errors: errors.filter((x) => !inF29(x)), http_errors: f29Http, outside_f29_http: http.filter((x) => !inF29(x)), mismatches };
writeFileSync(join(OUT, 'ui_check.json'), JSON.stringify(report, null, 1));
console.log(JSON.stringify({ n_pages: pages.length, errors: f29Errors.length, outside_f29: report.outside_f29_errors.length, http_errors: f29Http.length, mismatches, ms: pages.map((p) => p.ms) }));
process.exit(f29Errors.length || f29Http.length || mismatches.length || pages.length < 2 ? 1 : 0);
