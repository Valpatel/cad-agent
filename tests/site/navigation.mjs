/** The one navigation function of the site browser suite (tests/site/website-browser.mjs and the layout/ helpers it
 * runs), and the per-part boundary that turns a failed navigation into a finding of its own part (#686).
 *
 * `navigate(page, url, options)` calls `page.goto(url, options)` with exactly the arguments given. On success it only
 * watched the page's own events: it writes nothing and asks the preview server nothing. On failure it keeps, within
 * about two seconds, what the browser and the preview server saw of that navigation, writes a receipt under
 * /tmp/cad-agent-navigation-* (the CI job uploads /tmp/cad-agent-*), prints one evidence line and rethrows the
 * original error unchanged. A fault in the evidence is recorded in it, never thrown over the navigation's error.
 *
 * `fetchThrough(route)` does the same for a test-side `route.fetch` (the preview server's record of the path and its
 * sockets), aborts the route and adds the failure to its part's findings; `partHandler` wraps a route handler so
 * such a failure belongs to the part that registered it instead of crashing the run as an unhandled rejection.
 *
 * `runPart(name, action)` runs one part of the suite. A part that ends on a failed navigation reports one finding,
 * which keeps the original message, and its own browser contexts are closed; any other error propagates as before.
 * Nothing here retries a navigation, changes its timeout or turns a failure into a pass: the finding fails the run.
 * The receipt says what each side recorded; it does not say why a navigation stalled. */
import { AsyncLocalStorage } from 'node:async_hooks';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

const parts = new AsyncLocalStorage();
const failures = new WeakMap();   // the original error -> { error, evidence, receipt }
let sources = {};                 // { serverEvidence(pathname, since), testLag: [{ at, lateMs }] }

/** The preview server's record and this process's lag, which only the suite's entry point can reach. */
export function configureNavigation({ serverEvidence, testLag } = {}) { sources = { serverEvidence, testLag }; }

/** URLs as the receipts keep them: origin and path, no credentials, query or fragment. */
export const cleanURL = value => {
  if (value === 'about:blank') return value;
  try { const u = new URL(value); return /^https?:$/.test(u.protocol) ? (u.origin + u.pathname).slice(0, 300) : u.protocol; }
  catch { return '[unavailable URL]'; }
};
/** Text as the receipts keep it: every URL in it cleaned, at most 300 characters. */
export const cleanText = value => String(value).replace(/https?:\/\/[^\s"'<>]+/g, cleanURL).slice(0, 300);

/** At most `ms` for one piece of evidence; the timer never outlives it. */
const bounded = async (action, ms, what) => {
  let timer;
  try {
    return await Promise.race([Promise.resolve().then(action), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`${what} exceeded ${ms} ms`)), ms);
    })]);
  } finally { clearTimeout(timer); }
};

/** The page's own state when the navigation failed: which document, how far it got, its styles, fonts and images. */
function domSnapshot() {
  const nav = document.querySelector('cad-nav'), panel = document.querySelector('.cad-nav-panel');
  const css = node => node ? { display: getComputedStyle(node).display, position: getComputedStyle(node).position, overflowY: getComputedStyle(node).overflowY } : null;
  return { readyState: document.readyState, body: !!document.body, fontSet: document.fonts?.status || 'unavailable',
    fonts: [...(document.fonts || [])].slice(0, 12).map(f => ({ family: f.family, status: f.status })),
    styleCount: document.styleSheets.length,
    styles: [...document.querySelectorAll('link[rel=stylesheet]')].slice(0, 12).map(l => ({ href: l.href, sheet: !!l.sheet })),
    images: [...document.images].slice(0, 12).map(i => ({ href: i.src, complete: i.complete, width: i.naturalWidth })),
    navPresent: !!nav, navReady: nav?.hasAttribute('data-ready') || false, navStyle: css(nav), panelStyle: css(panel) };
}

/** `page.goto(url, options)`, and on failure the evidence of both sides before the original error is rethrown.
 * `diag`: `where` (which iteration, for people), `viewport` and `javaScriptEnabled` (as the caller set them),
 * `evidence` (a folder for the receipt instead of a new /tmp/cad-agent-navigation-*), and `plantEvidenceFault`
 * (the planted control's fault inside the evidence collection). */
export async function navigate(page, url, options, diag = {}) {
  const began = Date.now(), pending = new Map(), active = new WeakSet(), listeners = [];
  const events = { responses: [], failed: [], console: [], pageerror: [], lifecycle: [], committed: [], observerErrors: [] };
  const counts = Object.fromEntries(Object.keys(events).map(k => [k, 0]));
  let pendingCount = 0;
  const record = (kind, row) => { counts[kind]++; if (events[kind].length < 24) events[kind].push({ atMs: Date.now() - began, ...row() }); };
  const watch = (name, callback) => {
    const guarded = value => { try { callback(value); } catch (error) { record('observerErrors', () => ({ message: cleanText(error.message) })); } };
    listeners.push([name, guarded]); page.on(name, guarded);
  };
  const requestInfo = request => ({ url: cleanURL(request.url()), method: cleanText(request.method()), type: cleanText(request.resourceType()) });
  const finish = request => { if (active.delete(request)) pendingCount--; pending.delete(request); };
  watch('request', request => {
    if (!active.has(request)) { active.add(request); pendingCount++; }
    if (pending.size < 24) pending.set(request, { ...requestInfo(request), startedAt: Date.now() });
  });
  watch('requestfinished', finish);
  watch('requestfailed', request => { finish(request); record('failed', () => ({ ...requestInfo(request), error: cleanText(request.failure()?.errorText || 'unknown') })); });
  watch('response', response => {
    const entry = pending.get(response.request());
    if (entry) Object.assign(entry, { status: response.status(), respondedAt: Date.now() });
    record('responses', () => ({ url: cleanURL(response.url()), status: response.status(), navigation: response.request().isNavigationRequest() }));
  });
  watch('console', message => record('console', () => ({ type: cleanText(message.type()), text: cleanText(message.text()) })));
  watch('pageerror', error => record('pageerror', () => ({ message: cleanText(error.message) })));
  watch('framenavigated', frame => { if (frame === page.mainFrame()) record('committed', () => ({ url: cleanURL(frame.url()) })); });
  for (const name of ['domcontentloaded', 'load', 'crash', 'close']) watch(name, () => record('lifecycle', () => ({ name })));
  try {
    return await (options === undefined ? page.goto(url) : page.goto(url, options));
  } catch (error) {
    // Known as a failed navigation before any evidence is taken, so even broken evidence code leaves it a finding.
    const kept = { error, evidence: null, receipt: null };
    if (error && typeof error === 'object') failures.set(error, kept);
    try { await keepEvidence(error, kept, { page, url, options, diag, began, pending, events, counts, pendingCount: () => pendingCount }); }
    catch (fault) {   // keepEvidence records its own faults; this is the fault it could not record
      kept.evidenceError = cleanText(fault?.stack || fault);
      try { console.log('Navigation failure evidence unavailable: ' + kept.evidenceError.split('\n')[0]); } catch { /* never over the error */ }
    }
    throw error;
  } finally {
    for (const [name, callback] of listeners) page.off(name, callback);
  }
}

async function keepEvidence(error, kept, { page, url, options, diag, began, pending, events, counts, pendingCount }) {
  const scope = parts.getStore(), failed = Date.now();
  const pendingNow = () => [...pending.values()].map(entry => ({ ...entry, ageMs: failed - entry.startedAt }));
  const evidence = { part: scope?.name ?? null, where: diag.where ?? null, url: cleanURL(url),
    waitUntil: options?.waitUntil ?? 'load', timeout: options?.timeout ?? 'the page default (30000 ms unless the context changed it)',
    began, elapsedMs: failed - began, error: { name: cleanText(error?.name), message: cleanText(error?.message) }, captureErrors: [] };
  if (diag.viewport !== undefined) evidence.viewport = diag.viewport;
  if (diag.javaScriptEnabled !== undefined) evidence.javaScriptEnabled = diag.javaScriptEnabled;
  let folder = diag.evidence;
  try {
    if (diag.plantEvidenceFault) throw new Error('planted evidence-collection fault');
    evidence.currentURL = '[unavailable URL]';
    try { evidence.currentURL = cleanURL(page.url()); } catch (fault) { evidence.captureErrors.push('URL: ' + cleanText(fault.message)); }
    // whether the main frame committed any document since this navigation began, and whether the page is now on the
    // URL it was sent to (it can be, without a commit, when it was already there)
    evidence.committed = { sinceBegan: counts.committed > 0, pageOnTarget: evidence.currentURL === evidence.url };
    try {
      const browser = page.context().browser();
      evidence.viewport ??= page.viewportSize();
      evidence.engine = browser ? { name: browser.browserType().name(), version: browser.version() } : { unavailable: 'no browser behind this page' };
    } catch (fault) { evidence.engine = { unavailable: cleanText(fault.message) }; }
    try {
      const lag = sources.testLag ? sources.testLag.filter(l => l.at >= began) : null;
      evidence.testProcessLag = lag ? { maxMs: Math.max(0, ...lag.map(l => l.lateMs)), samplesOver20ms: lag.slice(-10) }
        : { unavailable: 'no test-process lag record configured' };
    } catch (fault) { evidence.testProcessLag = { unavailable: cleanText(fault.message) }; }
    try { folder ??= await mkdtemp(path.join(tmpdir(), 'cad-agent-navigation-')); }
    catch (fault) { evidence.captureErrors.push('receipt folder: ' + cleanText(fault.message)); }
    // The DOM, a screenshot and the server's record at once, each bounded, so the whole costs about two seconds.
    const server = sources.serverEvidence
      ? bounded(() => sources.serverEvidence(new URL(url).pathname, began - 1000), 2500, 'server record')
      : Promise.resolve({ unavailable: 'no preview server record configured' });
    const [dom, png, record] = await Promise.allSettled([
      bounded(() => page.evaluate(domSnapshot), 1000, 'diagnostic capture'),
      bounded(() => page.screenshot({ type: 'png', fullPage: false, timeout: 1000 }), 1000, 'diagnostic capture'),
      server]);
    if (dom.status === 'fulfilled') {
      evidence.dom = dom.value;
      try { evidence.dom.styles = evidence.dom.styles?.map(({ href, ...sheet }) => ({ ...sheet, href: href ? cleanURL(href) : null, path: href ? new URL(href).pathname : null })); }
      catch (fault) { evidence.captureErrors.push('DOM styles: ' + cleanText(fault.message)); }
      try { evidence.dom.images = evidence.dom.images?.map(({ href, ...image }) => ({ ...image, href: cleanURL(href) })); }
      catch (fault) { evidence.captureErrors.push('DOM images: ' + cleanText(fault.message)); }
    } else evidence.captureErrors.push('DOM: ' + cleanText(dom.reason?.message));
    if (png.status === 'rejected') evidence.captureErrors.push('screenshot: ' + cleanText(png.reason?.message));
    else if (png.value.length > 2 * 1024 * 1024) evidence.captureErrors.push('screenshot exceeded 2 MiB; not retained');
    else if (folder) {
      try { await writeFile(path.join(folder, 'navigation-failure.png'), png.value); evidence.screenshot = 'navigation-failure.png'; }
      catch (fault) { evidence.captureErrors.push('screenshot: ' + cleanText(fault.message)); }
    }
    evidence.server = record.status === 'fulfilled' ? record.value : { unavailable: cleanText(record.reason?.message) };
    // said in words, so an empty `matching` is not read as "never received" when the record does not reach back
    if (evidence.server && 'coversWindow' in evidence.server) evidence.server.coverage = evidence.server.coversWindow
      ? 'the server record covers every request received since 1 s before this navigation began'
      : 'NOT COVERED: the server dropped requests received since 1 s before this navigation began, so a missing request proves nothing';
  } catch (fault) { evidence.evidenceError = cleanText(fault?.stack || fault); }
  // The browser's record as it stands after the captures (a late response still counts); elapsedMs stays the failure's.
  evidence.pendingCount = pendingCount(); evidence.pending = pendingNow(); evidence.counts = { ...counts }; evidence.events = events;
  try {
    folder ??= await mkdtemp(path.join(tmpdir(), 'cad-agent-navigation-'));
    evidence.receipt = folder;
    await writeFile(path.join(folder, 'navigation-failure.json'), JSON.stringify(evidence, null, 2) + '\n');
  } catch (fault) { evidence.receipt = null; evidence.captureErrors.push('receipt: ' + cleanText(fault.message)); }
  Object.assign(kept, { evidence, receipt: evidence.receipt });
  try { console.log('Navigation failure evidence: ' + JSON.stringify(evidenceLine(evidence))); }
  catch (fault) { console.log('Navigation failure evidence unavailable: ' + cleanText(fault.message)); }
}

/** One line for the log: enough to tell which side stalled without opening the receipt. */
function evidenceLine(e) {
  const s = e.server ?? {}, at = r => ({ id: r.id, receivedMs: r.receivedAt - e.began, status: r.status ?? null,
    headersMs: r.headersAt ? r.headersAt - r.receivedAt : null, finishedMs: r.finishedAt ? r.finishedAt - r.receivedAt : null, socket: r.socket?.id ?? r.socket });
  return { part: e.part, where: e.where, url: e.url, waitUntil: e.waitUntil, elapsedMs: e.elapsedMs, engine: e.engine,
    currentURL: e.currentURL, committed: e.committed, pendingCount: e.pendingCount,
    pendingDocuments: e.pending.filter(r => r.type === 'document').map(r => ({ url: r.url, ageMs: r.ageMs, status: r.status ?? null })),
    failed: e.events.failed.length, testLagMaxMs: e.testProcessLag?.maxMs ?? null,
    server: s.unavailable ? { unavailable: s.unavailable } : { coversWindow: s.coversWindow, openSockets: s.openSockets,
      matchingFirst: s.matchingFirst?.map(at), matchingLast: s.matching?.slice(-3).map(at), requests: s.window?.requests,
      unanswered: s.window?.unanswered?.length, unfinished: s.window?.unfinished,
      socketsWithoutRequest: s.window?.socketsWithoutRequest?.length, lagMaxMs: s.lag?.maxMs },
    evidenceError: e.evidenceError, captureErrors: e.captureErrors.length ? e.captureErrors : undefined, receipt: e.receipt };
}

/** The failed navigation behind `error`, or behind its cause or the errors it aggregates: { error, evidence, receipt }. */
export function navigationFailure(error, seen = new Set()) {
  if (!error || typeof error !== 'object' || seen.has(error) || seen.size > 20) return null;
  seen.add(error);
  if (failures.has(error)) return failures.get(error);
  for (const inner of [error.cause, ...(Array.isArray(error.errors) ? error.errors : [])]) {
    const found = navigationFailure(inner, seen);
    if (found) return found;
  }
  return null;
}

/** Count each browser context a part opens (browser.newPage opens one too) as that part's, so a part stopped by a
 * failed navigation can have exactly its own closed, never the other lane's. */
export function ownContexts(browser) {
  const newContext = browser.newContext.bind(browser);
  browser.newContext = async (...args) => {
    const context = await newContext(...args);
    parts.getStore()?.contexts.add(context);
    return context;
  };
}

/** A route handler (page.route, context.route) that runs as part of the part that registered it, so a test-side fetch
 * that fails inside it (fetchThrough) is reported by that part instead of crashing the run as an unhandled
 * rejection. The failed fetch has already been recorded and its route aborted; any other error propagates as before. */
export function partHandler(handler) {
  const scope = parts.getStore();
  return async (...args) => {
    try { return await (scope ? parts.run(scope, () => handler(...args)) : handler(...args)); }
    catch (error) { if (!navigationFailure(error)) throw error; }
  };
}

/** `route.fetch(options)` from the test process to the preview server. On failure: the server's record of the path
 * and its sockets, and this process's lag, in a receipt under /tmp/cad-agent-navigation-*; one evidence line; the
 * failure added to the current part's findings; the route aborted, so the page sees a failed request instead of
 * one that never ends; then the original error rethrown unchanged. No second attempt is made. */
export async function fetchThrough(route, options) {
  const began = Date.now();
  try { return await (options === undefined ? route.fetch() : route.fetch(options)); }
  catch (error) {
    const kept = { error, evidence: null, receipt: null, kind: 'fetch' };
    if (error && typeof error === 'object') failures.set(error, kept);
    parts.getStore()?.failures.push(error);
    try {
      let url = '[unavailable URL]', method;
      try { url = route.request().url(); method = route.request().method(); } catch { /* recorded as unavailable */ }
      const evidence = kept.evidence = { kind: 'test-side fetch (route.fetch)', part: parts.getStore()?.name ?? null, url: cleanURL(url),
        method, began, elapsedMs: Date.now() - began, error: { name: cleanText(error?.name), message: cleanText(error?.message) }, captureErrors: [] };
      evidence.testProcessLag = sources.testLag ? { maxMs: Math.max(0, ...sources.testLag.filter(l => l.at >= began - 1000).map(l => l.lateMs)) } : { unavailable: 'no test-process lag record configured' };
      try {
        evidence.server = sources.serverEvidence ? await bounded(() => sources.serverEvidence(new URL(url).pathname, began - 1000), 2500, 'server record')
          : { unavailable: 'no preview server record configured' };
      } catch (fault) { evidence.server = { unavailable: cleanText(fault.message) }; }
      try {
        const folder = await mkdtemp(path.join(tmpdir(), 'cad-agent-navigation-'));
        await writeFile(path.join(folder, 'fetch-failure.json'), JSON.stringify(evidence, null, 2) + '\n');
        evidence.receipt = kept.receipt = folder;
      } catch (fault) { evidence.captureErrors.push('receipt: ' + cleanText(fault.message)); }
      const s = evidence.server ?? {};
      console.log('Fetch failure evidence: ' + JSON.stringify({ part: evidence.part, url: evidence.url, method, elapsedMs: evidence.elapsedMs,
        error: evidence.error.message.split('\n')[0], testLagMaxMs: evidence.testProcessLag.maxMs ?? null,
        server: s.unavailable ? { unavailable: s.unavailable } : { coversWindow: s.coversWindow, openSockets: s.openSockets,
          matching: s.matching?.slice(-3).map(r => ({ id: r.id, receivedMs: r.receivedAt - began, status: r.status ?? null, finished: !!r.finishedAt, aborted: !!r.aborted, socket: r.socket?.id ?? r.socket })),
          unanswered: s.window?.unanswered?.length, unfinished: s.window?.unfinished, socketsClosedIdle: s.window?.socketsClosedIdle,
          socketsWithoutRequest: s.window?.socketsWithoutRequest?.length, lagMaxMs: s.lag?.maxMs },
        receipt: evidence.receipt }));
    } catch (fault) { kept.evidenceError = cleanText(fault?.stack || fault); }
    try { await route.abort('failed'); } catch { /* the page or route may already be gone */ }
    throw error;
  }
}

/** The finding for a failed navigation or test-side fetch: the original message first, then where its evidence is. */
function failureFinding(name, error, failure, stopped) {
  const original = failure.error, what = failure.kind === 'fetch' ? 'a test-side fetch failed' : 'a navigation failed';
  return `${name}: ${what}${stopped ? ', so this part stopped there' : ' (the part went on)'}: ${String(original.message).trim()}` +
    (error !== original ? `\n  raised as ${error.name}: ${String(error.message).split('\n')[0].slice(0, 300)}` : '') +
    `\n  ${failure.kind === 'fetch' ? 'fetch' : 'navigation'} evidence: ${failure.receipt ?? `no receipt (${failure.evidenceError ? `evidence collection failed: ${failure.evidenceError.split('\n')[0]}` : 'see the evidence line above'})`}`;
}

/** Run one part: its findings, plus one for each test-side fetch that failed in it (fetchThrough). A part that ends on
 * a failed navigation, or that throws after one of its fetches failed, reports that as its finding, keeping the
 * original message (and the error it was raised as, if a caller wrapped it), after closing the contexts the part left
 * open. Cleanup is bounded and its faults are added to the finding; they never replace it. Any other error
 * propagates. */
export async function runPart(name, action) {
  const scope = { name, contexts: new Set(), failures: [] };
  const fetched = () => scope.failures.map(error => failureFinding(name, error, navigationFailure(error), false));
  try { return [...await parts.run(scope, action), ...fetched()]; }
  catch (error) {
    const failure = navigationFailure(error);
    if (!failure && !scope.failures.length) throw error;
    const left = [...scope.contexts].filter(context => { try { return context.browser()?.contexts().includes(context) ?? true; } catch { return true; } });
    const closed = await Promise.allSettled(left.map(context => bounded(() => context.close(), 10000, 'closing a context')));
    const cleanup = closed.filter(result => result.status === 'rejected').map(result => cleanText(result.reason?.message));
    const findings = scope.failures.filter(fetchError => fetchError !== failure?.error).map(fetchError => failureFinding(name, fetchError, navigationFailure(fetchError), false));
    findings.push(failure ? failureFinding(name, error, failure, true)
      : `${name}: after a test-side fetch failed, this part stopped on: ${String(error?.stack || error).slice(0, 2000)}`);
    findings[findings.length - 1] += (left.length ? `\n  closed ${left.length - cleanup.length} of ${left.length} browser context(s) the part left open` : '') +
      (cleanup.length ? `; cleanup failed: ${cleanup.join('; ')}` : '');
    return findings;
  }
}
