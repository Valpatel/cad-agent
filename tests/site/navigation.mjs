/** The one navigation function of the site browser suite (tests/site/website-browser.mjs and the layout/ helpers it
 * runs), and the per-part boundary that turns a failed navigation into a finding of its own part (#686).
 *
 * `navigate(page, url, options)` calls `page.goto(url, options)` with exactly the arguments given. On success it only
 * watched the page's own events: it writes nothing and asks the preview server nothing. On failure it keeps, within
 * about two seconds, what the browser and the preview server saw of that navigation, writes a receipt under
 * /tmp/cad-agent-navigation-* (the CI job uploads /tmp/cad-agent-*), prints one evidence line and rethrows the
 * original error unchanged. A fault in the evidence is recorded in it, never thrown over the navigation's error.
 * For the main frame's document requests the receipt says which of Playwright's events (request, response,
 * requestfinished, requestfailed) each got and when, which routes the page and its context had, and, for a request a
 * route handler took, when the handler ran and ended and how each fetch, fulfill or continue it made settled
 * (`watchRoutes`). Most of the suite's navigations pass through no route handler at all: the receipt says so.
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
let sources = {};                 // { serverEvidence(pathname, since), testLag: [{ at, lateMs }], fullEvidenceLimit }
let fullEvidenceKept = 0;

/** The preview server's record and this process's lag, which only the suite's entry point can reach, and how many
 * failures in a run keep full evidence (DOM, screenshot and receipt): after that, only the evidence line, with the
 * browser's and the server's record. A part that goes on after each failed navigation (wide layouts catches each of
 * its 40) cannot then keep 40 screenshots. Planted controls and probes that bring their own folder do not count. */
export function configureNavigation({ serverEvidence, testLag, fullEvidenceLimit = Infinity } = {}) {
  sources = { serverEvidence, testLag, fullEvidenceLimit };
  fullEvidenceKept = 0;
}

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
 * `evidence` (a folder for the receipt instead of a new /tmp/cad-agent-navigation-*), `planted` (a planted control:
 * always full evidence, not counted against fullEvidenceLimit) and `plantEvidenceFault` (the planted control's fault
 * inside the evidence collection). */
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
  // The main frame's document requests (at most 8), and which of Playwright's events each one got: the record of the
  // hop between the browser's network stack and the test process (#686). Only times are kept on the way.
  const documents = new Map();
  const documentOf = request => documents.get(request);
  const finish = request => { if (active.delete(request)) pendingCount--; pending.delete(request); };
  watch('request', request => {
    if (!active.has(request)) { active.add(request); pendingCount++; }
    if (pending.size < 24) pending.set(request, { ...requestInfo(request), startedAt: Date.now() });
    let main = false;   // a service worker's request has no frame, and frame() throws for it
    try { main = documents.size < 8 && request.isNavigationRequest() && request.frame() === page.mainFrame(); } catch { /* not the main frame's */ }
    if (main) documents.set(request, { url: request.url(), requestAt: Date.now() });
  });
  watch('requestfinished', request => { finish(request); const d = documentOf(request); if (d) d.finishedAt = Date.now(); });
  watch('requestfailed', request => {
    finish(request);
    const d = documentOf(request);
    if (d) Object.assign(d, { failedAt: Date.now(), failure: request.failure()?.errorText ?? 'unknown' });
    record('failed', () => ({ ...requestInfo(request), error: cleanText(request.failure()?.errorText || 'unknown') }));
  });
  watch('response', response => {
    const d = documentOf(response.request());
    if (d) Object.assign(d, { respondedAt: Date.now(), status: response.status() });
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
    try { await keepEvidence(error, kept, { page, url, options, diag, began, pending, documents, events, counts, pendingCount: () => pendingCount }); }
    catch (fault) {   // keepEvidence records its own faults; this is the fault it could not record
      kept.evidenceError = cleanText(fault?.stack || fault);
      try { console.log('Navigation failure evidence unavailable: ' + kept.evidenceError.split('\n')[0]); } catch { /* never over the error */ }
    }
    throw error;
  } finally {
    for (const [name, callback] of listeners) page.off(name, callback);
  }
}

async function keepEvidence(error, kept, { page, url, options, diag, began, pending, documents, events, counts, pendingCount }) {
  const scope = parts.getStore(), failed = Date.now();
  const pendingNow = () => [...pending.values()].map(entry => ({ ...entry, ageMs: failed - entry.startedAt }));
  const evidence = { part: scope?.name ?? null, where: diag.where ?? null, url: cleanURL(url),
    waitUntil: options?.waitUntil ?? 'load', timeout: options?.timeout ?? 'the page default (30000 ms unless the context changed it)',
    began, elapsedMs: failed - began, error: { name: cleanText(error?.name), message: cleanText(error?.message) }, captureErrors: [] };
  if (diag.viewport !== undefined) evidence.viewport = diag.viewport;
  if (diag.javaScriptEnabled !== undefined) evidence.javaScriptEnabled = diag.javaScriptEnabled;
  let folder = diag.evidence;
  const full = diag.planted || diag.evidence !== undefined || ++fullEvidenceKept <= (sources.fullEvidenceLimit ?? Infinity);
  if (!full) evidence.fullEvidence = `skipped: the first ${sources.fullEvidenceLimit} failures in this run kept theirs`;
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
    if (full) {
      try { folder ??= await mkdtemp(path.join(tmpdir(), 'cad-agent-navigation-')); }
      catch (fault) { evidence.captureErrors.push('receipt folder: ' + cleanText(fault.message)); }
    }
    // The DOM, a screenshot and the server's record at once, each bounded, so the whole costs about two seconds.
    const server = sources.serverEvidence
      ? bounded(() => sources.serverEvidence(new URL(url).pathname, began - 1000), 2500, 'server record')
      : Promise.resolve({ unavailable: 'no preview server record configured' });
    const skipped = Promise.reject(new Error('not taken: full evidence skipped'));
    skipped.catch(() => {});
    const hops = routeHopsOf(page, began);
    const [dom, png, record, , planted] = await Promise.allSettled([
      full ? bounded(() => page.evaluate(domSnapshot), 1000, 'diagnostic capture') : skipped,
      full ? bounded(() => page.screenshot({ type: 'png', fullPage: false, timeout: 1000 }), 1000, 'diagnostic capture') : skipped,
      server,
      bounded(() => hopBodySizes(hops), 1000, 'route fetch body sizes'),
      // a planted control's action at the moment the navigation has failed (a late fulfil), before the record is read
      diag.planted && diag.afterFailure ? bounded(diag.afterFailure, 1000, 'planted after-failure action') : Promise.resolve()]);
    if (planted.status === 'rejected') evidence.captureErrors.push('planted after-failure action: ' + cleanText(planted.reason?.message));
    if (!full) { /* the DOM and screenshot were not taken */ }
    else if (dom.status === 'fulfilled') {
      evidence.dom = dom.value;
      try { evidence.dom.styles = evidence.dom.styles?.map(({ href, ...sheet }) => ({ ...sheet, href: href ? cleanURL(href) : null, path: href ? new URL(href).pathname : null })); }
      catch (fault) { evidence.captureErrors.push('DOM styles: ' + cleanText(fault.message)); }
      try { evidence.dom.images = evidence.dom.images?.map(({ href, ...image }) => ({ ...image, href: cleanURL(href) })); }
      catch (fault) { evidence.captureErrors.push('DOM images: ' + cleanText(fault.message)); }
    } else evidence.captureErrors.push('DOM: ' + cleanText(dom.reason?.message));
    if (!full) { /* no screenshot */ }
    else if (png.status === 'rejected') evidence.captureErrors.push('screenshot: ' + cleanText(png.reason?.message));
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
  try { Object.assign(evidence, documentRecord(page, began, documents)); }
  catch (fault) { evidence.documents = { unavailable: cleanText(fault?.message) }; }
  if (!full) evidence.receipt = null;
  else try {
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
  return { part: e.part, where: e.where, url: e.url, error: e.error.message.split('\n')[0], waitUntil: e.waitUntil, elapsedMs: e.elapsedMs, engine: e.engine,
    currentURL: e.currentURL, committed: e.committed, pendingCount: e.pendingCount,
    pendingDocuments: e.pending.filter(r => r.type === 'document').map(r => ({ url: r.url, ageMs: r.ageMs, status: r.status ?? null })),
    routing: e.routing, documents: Array.isArray(e.documents) ? e.documents.map(documentLine) : e.documents,
    routeHops: e.routeHops?.length ? e.routeHops : undefined,
    failed: e.events.failed.length, testLagMaxMs: e.testProcessLag?.maxMs ?? null,
    server: s.unavailable ? { unavailable: s.unavailable } : { coversWindow: s.coversWindow, openSockets: s.openSockets,
      matchingFirst: s.matchingFirst?.map(at), matchingLast: s.matching?.slice(-3).map(at), requests: s.window?.requests,
      unanswered: s.window?.unanswered?.length, unfinished: s.window?.unfinished,
      socketsWithoutRequest: s.window?.socketsWithoutRequest?.length, lagMaxMs: s.lag?.maxMs },
    evidenceError: e.evidenceError, captureErrors: e.captureErrors.length ? e.captureErrors : undefined, fullEvidence: e.fullEvidence, receipt: e.receipt };
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
 * failed navigation can have exactly its own closed, never the other lane's. A context opened from a Playwright event
 * listener (page.on) or from a route handler not wrapped with partHandler runs outside any part: it belongs to no
 * part and stays open until the browser closes. Wrap such handlers with partHandler. */
export function ownContexts(browser) {
  const newContext = browser.newContext.bind(browser);
  browser.newContext = async (...args) => {
    const context = await newContext(...args);
    parts.getStore()?.contexts.add(context);
    return context;
  };
}

/* Route hops (#686). Which hop loses a stalled document: the route handler never called, its fetch never returned,
 * its fulfil (or continue) resolved or threw while the page never committed, or no handler at all. watchRoutes(browser)
 * wraps route, unroute and unrouteAll on every context the browser opens and on every page those contexts open, so a
 * failed navigation's receipt can say which routes the page and its context had, and for each navigation request a
 * handler took: when each handler ran and ended, and each fetch, fulfill, continue, abort or fallback it made, when
 * it was called, and when and how it settled. A request that is not a navigation request passes straight through, so
 * on the success path the cost is one isNavigationRequest() per routed request. The record is bounded: weak maps
 * keyed by Playwright's own objects, at most 8 hops per page, 4 handlers and 8 calls per hop. Recording never throws
 * into a handler and never changes what a handler or a route method returns or throws.
 * Limits: a route registered with `times` stays listed after Playwright drops it, and Playwright itself continues a
 * request no pattern matches, inside its driver, a hop the test process cannot see. */
const routeTables = new WeakMap();   // a page or context -> [{ url, pattern, handler, wrapped }]
const hopsByPage = new WeakMap();    // a page -> its last 8 route hops for navigation requests
const hopOf = new WeakMap();         // a Playwright Request -> its hop
const wrappedRoutes = new WeakSet(); // routes whose methods are already recorded
const ROUTE_METHODS = ['fetch', 'fulfill', 'continue', 'abort', 'fallback'];
const firstLine = error => cleanText(String(error?.message ?? error).split('\n')[0]);   // Playwright's call log follows
const describePattern = url => typeof url === 'string' ? cleanText(url) : url instanceof RegExp ? cleanText(String(url)).slice(0, 120) : typeof url === 'function' ? '[a URL predicate]' : cleanText(String(url));

/** Record the route hops of every context `browser` opens from now on, and of the pages those contexts open. */
export function watchRoutes(browser) {
  const newContext = browser.newContext.bind(browser);
  browser.newContext = async (...args) => {
    const context = await newContext(...args);
    try {
      watchTarget(context);
      const newPage = context.newPage.bind(context);
      context.newPage = async (...pageArgs) => { const page = await newPage(...pageArgs); try { watchTarget(page); } catch { /* unwatched */ } return page; };
    } catch { /* this context's routes stay unwatched; its receipts say so */ }
    return context;
  };
}

/** Wrap one page's or context's route, unroute and unrouteAll (exported for the unit tests). */
export function watchTarget(target) {
  if (routeTables.has(target)) return target;
  const table = [], route = target.route.bind(target), unroute = target.unroute.bind(target), unrouteAll = target.unrouteAll.bind(target);
  target.route = (url, handler, ...rest) => {
    const entry = { url, pattern: describePattern(url), handler, wrapped: hopHandler(handler, describePattern(url)) };
    table.push(entry);
    return route(url, entry.wrapped, ...rest);
  };
  target.unroute = (url, handler) => {
    const gone = table.filter(e => e.url === url && (handler === undefined || e.handler === handler));
    for (const e of gone) table.splice(table.indexOf(e), 1);
    if (handler === undefined || !gone.length) return handler === undefined ? unroute(url) : unroute(url, handler);
    return Promise.all(gone.map(e => unroute(url, e.wrapped))).then(() => {});
  };
  target.unrouteAll = (...args) => { table.length = 0; return unrouteAll(...args); };
  routeTables.set(target, table);
  return target;
}

/** `handler`, recording when it ran and ended for a navigation request; any other request goes straight to it. */
function hopHandler(handler, pattern) {
  return function (route, ...rest) {
    const row = startHop(route, pattern);
    if (!row) return handler.call(this, route, ...rest);
    const end = (outcome, error) => { try { Object.assign(row, { endedAt: Date.now(), outcome }, error && { error: firstLine(error) }); } catch { /* never over the handler */ } };
    let result;
    try { result = handler.call(this, route, ...rest); }
    catch (error) { end('threw', error); throw error; }
    return Promise.resolve(result).then(value => { end('returned'); return value; }, error => { end('threw', error); throw error; });
  };
}

function startHop(route, pattern) {
  try {
    const request = route.request();
    if (!request.isNavigationRequest()) return null;
    let hop = hopOf.get(request);
    if (!hop) {
      hop = { url: cleanURL(request.url()), at: Date.now(), handlers: [], calls: [], callsDropped: 0 };
      hopOf.set(request, hop);
      try {
        const page = request.frame().page();
        const ring = hopsByPage.get(page) ?? [];
        hopsByPage.set(page, ring);
        ring.push(hop);
        if (ring.length > 8) ring.shift();
      } catch { /* a request with no page: kept by its request only */ }
    }
    if (!wrappedRoutes.has(route)) { wrappedRoutes.add(route); recordRouteCalls(route, hop); }
    const row = { pattern, at: Date.now(), endedAt: null, outcome: 'running' };
    if (hop.handlers.length < 4) hop.handlers.push(row);
    return row;
  } catch { return null; }   // recording failed: the handler runs as if unwatched
}

/** Own-property wrappers over the route's fetch, fulfill, continue, abort and fallback, recording each call. */
function recordRouteCalls(route, hop) {
  for (const method of ROUTE_METHODS) {
    const original = route[method];
    if (typeof original !== 'function') continue;
    route[method] = function (...args) {
      let call = null;
      try { call = { method, at: Date.now(), settledAt: null, outcome: 'pending' }; if (hop.calls.length < 8) hop.calls.push(call); else hop.callsDropped++; }
      catch { /* unrecorded */ }
      const settle = (outcome, extra) => { try { if (call) Object.assign(call, { settledAt: Date.now(), outcome }, extra); } catch { /* never over the call */ } };
      let result;
      try { result = original.apply(route, args); }
      catch (error) { settle('threw', { error: firstLine(error) }); throw error; }
      return Promise.resolve(result).then(value => {
        if (method !== 'fetch') settle('resolved');
        else {
          let status = null; try { status = value.status(); } catch { /* not a response */ }
          settle('resolved', { status });
          try { if (call) Object.defineProperty(call, 'response', { value, enumerable: false }); } catch { /* no body size then */ }
        }
        return value;
      }, error => { settle('threw', { error: firstLine(error) }); throw error; });
    };
  }
}

/** The route hops of `page`'s navigation requests since `since`. */
const routeHopsOf = (page, since) => { try { return (hopsByPage.get(page) ?? []).filter(hop => hop.at >= since); } catch { return []; } };

/** Each fetched response's body size, read only once a navigation has failed (the success path never reads it). */
async function hopBodySizes(hops) {
  for (const hop of hops) for (const call of hop.calls) {
    if (!call.response || call.bodyBytes !== undefined) continue;
    try { call.bodyBytes = (await call.response.body()).length; } catch (fault) { call.bodyError = cleanText(fault?.message ?? fault); }
  }
}

const hopRow = (hop, began) => {
  const ms = t => (t ? t - began : null);
  return { url: hop.url,
    handlers: hop.handlers.map(h => ({ pattern: h.pattern, ranAtMs: ms(h.at), endedAtMs: ms(h.endedAt), outcome: h.outcome, ...(h.error && { error: h.error }) })),
    calls: hop.calls.map(c => ({ method: c.method, calledAtMs: ms(c.at), settledAtMs: ms(c.settledAt), outcome: c.outcome,
      ...(c.status !== undefined && { status: c.status }), ...(c.bodyBytes !== undefined && { bodyBytes: c.bodyBytes }),
      ...(c.bodyError && { bodyError: c.bodyError }), ...(c.error && { error: c.error }) })),
    ...(hop.callsDropped && { callsDropped: hop.callsDropped }) };
};

/** Which routes the page and its context had when the navigation failed. */
function routingOf(page) {
  let context = null;
  try { context = page.context(); } catch { /* none to read */ }
  const list = target => (target && routeTables.has(target) ? routeTables.get(target).slice(0, 16).map(e => e.pattern) : null);
  const onPage = list(page), onContext = list(context);
  if (onPage === null && onContext === null)
    return { watched: false, note: 'routes are not watched for this page (watchRoutes), so whether its requests passed through a route handler is not known' };
  return { watched: true, page: onPage ?? [], context: onContext ?? [] };
}

/** The main frame's document requests: Playwright's events for each, and the route hop it took (or why it took none). */
function documentRecord(page, began, documents) {
  const ms = t => (t ? t - began : null), routing = routingOf(page), hops = routeHopsOf(page, began), shown = new Set();
  const routed = routing.watched && routing.page.length + routing.context.length > 0;
  const rows = [...documents].map(([request, d]) => {
    const hop = hopOf.get(request);
    if (hop) shown.add(hop);
    let timing;
    try { const t = request.timing(); timing = Object.fromEntries(Object.entries(t).map(([k, v]) => [k, typeof v === 'number' ? Math.round(v) : null])); }
    catch { timing = null; }
    return { url: cleanURL(d.url), requestAtMs: ms(d.requestAt), responseAtMs: ms(d.respondedAt), status: d.status ?? null,
      finishedAtMs: ms(d.finishedAt), failedAtMs: ms(d.failedAt), ...(d.failure && { failure: cleanText(d.failure) }),
      events: { request: true, response: !!d.respondedAt, requestfinished: !!d.finishedAt, requestfailed: !!d.failedAt }, timing,
      route: hop ? hopRow(hop, began) : !routing.watched ? 'not known: routes are not watched for this page'
        : routed ? 'no handler of the test process ran for it, though the page or its context has routes: Playwright continues a request no pattern matches inside its driver, a hop the test process cannot see'
        : 'no route on the page or its context: it did not pass through a route handler' };
  });
  // hops whose request Playwright never reported to the page's 'request' listeners
  return { routing, documents: rows, routeHops: hops.filter(hop => !shown.has(hop)).map(hop => hopRow(hop, began)) };
}

/** A document's row for the evidence line: the receipt keeps its timing too. */
const documentLine = ({ timing, ...row }) => row;

/** A route handler (page.route, context.route) that runs as part of the part that registered it, so a test-side fetch
 * that fails inside it (fetchThrough) is reported by that part instead of crashing the run as an unhandled
 * rejection. The failed fetch has already been recorded and its route aborted; any other error propagates as before. */
export function partHandler(handler) {
  const scope = parts.getStore();
  return async (...args) => {
    try { return await (scope ? parts.run(scope, () => handler(...args)) : handler(...args)); }
    catch (error) { if (!scope?.failures.includes(error)) throw error; }   // only what its part has recorded
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
    `\n  ${failure.kind === 'fetch' ? 'fetch' : 'navigation'} evidence: ${failure.receipt ?? `no receipt (${failure.evidenceError ? `evidence collection failed: ${failure.evidenceError.split('\n')[0]}` : failure.evidence?.fullEvidence ? `full evidence ${failure.evidence.fullEvidence}; see the evidence line above` : 'see the evidence line above'})`}`;
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

/** Run `parts` ([name, async () => findings]) `lanes` at a time, in the order given, and return their findings in that
 * order, with which parts finished. The log gives each part's time, so a slow one is easy to find. A part that ends on
 * a failed navigation or fetch reports it as its finding and the run goes on (runPart); a part that throws anything
 * else fails the run once the parts already started have finished, so no page is closed under a part still using
 * it. Before that error is thrown, the findings gathered so far are printed: a stall in one part must not vanish
 * behind another part's error. */
export async function inLanes(parts, { lanes = 2, label = 'browser' } = {}) {
  const found = parts.map(() => []), took = parts.map(() => 0), finished = parts.map(() => false), errors = [], start = Date.now();
  let next = 0;
  const lane = async () => {
    while (next < parts.length && !errors.length) {
      const i = next++, t = Date.now();
      console.log(`${label}: starting ${parts[i][0]}`);
      try { found[i] = await runPart(parts[i][0], parts[i][1]); finished[i] = true; } catch (e) { errors.push(e); }
      took[i] = Math.round((Date.now() - t) / 1000);
      console.log(`${label}: finished ${parts[i][0]} in ${took[i]} s; ${found[i].length} findings, ${errors.length} errors so far`);
    }
  };
  await Promise.all(Array.from({ length: lanes }, lane));
  console.log(`${label}: ${parts.length} parts, ${lanes} at a time, in ${Math.round((Date.now() - start) / 1000)} s: ${parts.map(([name], i) => `${name} ${took[i]} s`).join(', ')}`);
  if (errors.length) {
    const so = found.flat();
    console.log(`${label}: a part threw, so the run stops; ${so.length} finding(s) from the parts that finished first:` +
      (so.length ? '\n' + so.map(f => '- ' + f).join('\n') : ' none'));
    throw errors[0];
  }
  return { found, finished };
}
