# text-to-cad 2f793659fb -> 2f793659fb (MIT)

Full scan of 1864 files.
New findings (not in the reviewed baseline): HIGH 3, MEDIUM 1212, LOW 153. Suppressed by baseline: 0.

## HIGH

| rule | file:line | text |
|---|---|---|
| credential-read | `tests/python/global/test_release_gate.py:96` | `environment = {"GITHUB_REPOSITORY": "o/r", "GITHUB_REPOSITORY_ID": str(REPO_ID), "GITHUB_TOKEN": "t"}` |
| credential-read | `tests/python/packages/cadgen/viewer/test_security.py:52` | `self.write("id_rsa", SECRET)` |
| credential-read | `tests/python/packages/cadgen/viewer/test_security.py:230` | `for name in ("secrets.json", ".env", "id_rsa", "model.py", "loose.js", "part.anim.js", ".dotfile.step"):` |

## MEDIUM

| rule | file:line | text |
|---|---|---|
| telemetry | `AGENTS.md:48` | `maps to PostHog and the wheel to PyPI, and` |
| telemetry | `AGENTS.md:103` | `- `apps/api/`: `api.texttocad.dev`, its own Vercel project: cadgen's version feed (read from PyPI) and the CAD app's consented analytics.` |
| telemetry | `CONTRIBUTING.md:277` | `/ api / `apps/api`, `test-api.sh` / `npm --prefix apps/api test`: the version feed's and the telemetry receiver's tests (no install) /` |
| telemetry | `CONTRIBUTING.md:406` | `- `apps/api/` for `api.texttocad.dev`, the version feed and the telemetry receiver` |
| telemetry | `CONTRIBUTING.md:715` | `-- a page whose maps PostHog could not use stops the release here.` |
| telemetry | `CONTRIBUTING.md:720` | `5. **Source maps, then PyPI** (on `main` only). The maps go to PostHog first` |
| telemetry | `CONTRIBUTING.md:721` | `(`posthog-cli sourcemap upload`, pinned), each filed under its chunk's debug` |
| telemetry | `CONTRIBUTING.md:808` | `with telemetry and says a new release is out only to a copy that is not` |
| telemetry | `CONTRIBUTING.md:814` | `runtime, so a plugin that ships somewhere new writes its own, and the telemetry` |
| telemetry | `CONTRIBUTING.md:897` | `store or Gemini updates them. Telemetry passes through the same API to PostHog: a deploy (`Deploy API`, on every` |
| telemetry | `CONTRIBUTING.md:898` | `change to `apps/api` on `main`) needs the project's PostHog settings in Vercel, which` |
| telemetry | `CONTRIBUTING.md:1004` | `gate checks the same way: `POSTHOG_CLI_API_KEY`, a PostHog personal API key scoped to` |
| telemetry | `CONTRIBUTING.md:1005` | `the telemetry project with `error_tracking:write` alone (not the receiver's, which` |
| telemetry | `CONTRIBUTING.md:1006` | `lives in Vercel); `POSTHOG_CLI_PROJECT_ID`; and `POSTHOG_CLI_HOST`` |
| telemetry | `CONTRIBUTING.md:1007` | `(`https://us.posthog.com` or `https://eu.posthog.com`). Keep` |
| telemetry | `README.md:46` | ``uvx cadgen telemetry off`, or ask your agent to. [Telemetry](#telemetry) says` |
| telemetry | `README.md:284` | `never for a copy that something else updates. `CADGEN_UPDATE_CHECK=0` turns it off.` |
| telemetry | `README.md:286` | `### Telemetry` |
| telemetry | `README.md:299` | `comes from (worked out from its IP address, which it doesn't keep) and stores it all with PostHog. Never file names,` |
| telemetry | `README.md:301` | `also deletes what was sent, with `uvx cadgen telemetry off`, **Share usage stats** in either app's menu (the logo at` |
| telemetry | `README.md:302` | `the top left, over any model), or by asking your agent. `DO_NOT_TRACK=1` or `CADGEN_TELEMETRY=0` turns it off for` |
| telemetry | `README.md:303` | `one process, and `CADGEN_TELEMETRY=1` on, without changing your setting; nothing is sent by default in CI or from a` |
| telemetry | `README.md:306` | `of cadgen sends it in the background; turning telemetry off deletes them.` |
| telemetry | `apps/api/README.md:3` | ``api.texttocad.dev`: cadgen's version feed and its telemetry receiver, a Vercel` |
| telemetry | `apps/api/README.md:21` | `src/            # the handler, the receiver (events.mjs), the drop list (noise.mjs), PostHog's store, the feed; their tests` |
| telemetry | `apps/api/README.md:23` | `scripts/        # the one-off Neon-to-PostHog migration` |
| telemetry | `apps/api/README.md:43` | ``packages/cadgen`), and receive cadgen's telemetry (`cadgen/analytics.py`): the usage` |
| telemetry | `apps/api/README.md:45` | `daemon send, which it checks and passes on to PostHog. Clients know only` |
| telemetry | `apps/api/README.md:50` | `/ `GET /v1/versions` / The version feed, the same for everyone: `{latest}` → `200` (`src/versions.mjs`). `latest` is the newest `X.Y.Z` rele` |
| telemetry | `apps/api/README.md:51` | `/ `POST /v1/events` / One batch: `{schema: 5, batch, at, install, session, process, version, channel, platform, arch, client: {name, version` |
| telemetry | `apps/api/README.md:52` | `/ `POST /v1/forget` / `{install}`: deletes the install's person in PostHog and every event sent under its id → `204` once PostHog has queued` |
| telemetry | `apps/api/README.md:53` | `/ `GET /v1/health` / → `200`, or `503` naming a missing or malformed setting (`POSTHOG_REGION`, `POSTHOG_PROJECT_KEY`, `POSTHOG_PERSONAL_KEY` |
| telemetry | `apps/api/README.md:55` | `Each event of a batch becomes one PostHog event (`src/posthog.mjs`): `tool_used`, `tool_failed`,` |
| telemetry | `apps/api/README.md:57` | ``feature_used`, `daemon_health` or, for a crash, `$exception`, which PostHog's error tracking groups into` |
| telemetry | `apps/api/README.md:64` | `PostHog's own location lookup is off for every event (`$geoip_disable`): the receiver` |
| telemetry | `apps/api/README.md:69` | `**A batch sent again counts once.** A schema 5 row's event carries its row id as PostHog's `uuid`` |
| telemetry | `apps/api/README.md:70` | `and its batch's `at` as its `timestamp`, both the same however often the batch comes. PostHog takes` |
| telemetry | `apps/api/README.md:72` | `([its docs](https://posthog.com/docs/cdp/common-questions): sent with a uuid, duplicates "are eventually` |
| telemetry | `apps/api/README.md:84` | `sends PostHog none.` |
| telemetry | `apps/api/README.md:87` | `feature. Each refusal is one `console.warn` line: `telemetry /v1/events refused 400:` |
| telemetry | `apps/api/README.md:91` | `name or string code alone (`TimeoutError`, `posthog_503`).` |
| telemetry | `apps/api/README.md:95` | `PostHog with no fix in cadgen. A signature goes on the list only when it can never` |
| telemetry | `apps/api/README.md:97` | `the client stops sending it (`stdout_closed` and `signature` in `cadgen/analytics.py`). Each` |
| telemetry | `apps/api/README.md:110` | `by name: `telemetry dropped page_left 4, worker_stopped 1 (schema 3, cadgen 0.7.17)`.` |
| network | `apps/api/README.md:117` | `- **Portable.** `src/handler.mjs` is a plain `fetch(Request) → Response` handler` |
| telemetry | `apps/api/README.md:118` | `over a store (`insert`, `forget`, `ready`) and a feed (`versions`); `posthog.mjs` is` |
| telemetry | `apps/api/README.md:119` | `PostHog's, `versions.mjs` reads PyPI, and `api/v1.js` with `vercel.json` is all that` |
| telemetry | `apps/api/README.md:124` | `Setup, once: a PostHog project; the domain `api.texttocad.dev` on this Vercel` |
| telemetry | `apps/api/README.md:127` | ``POSTHOG_REGION` (`us` or `eu`, where the PostHog project lives),` |
| telemetry | `apps/api/README.md:128` | ``POSTHOG_PROJECT_KEY` (the project's API key, which captures), `POSTHOG_PERSONAL_KEY`` |
| telemetry | `apps/api/README.md:131` | ``POSTHOG_PROJECT_ID`. Nothing in GitHub holds them. A changed value takes effect with` |
| telemetry | `apps/api/README.md:133` | ``503` while any is missing, PostHog refuses the personal key, or the project key is` |
| telemetry | `apps/api/README.md:137` | `Retention is PostHog's: events go after the period its plan keeps them (a year on the` |
| telemetry | `apps/api/README.md:150` | `PostHog is down, a `404` before it is deployed, a firewall's `403` or a `429`) and sends` |
| telemetry | `apps/api/README.md:156` | `What it answers, in PostHog: how many people use CAD (installs: one per machine and OS` |
| telemetry | `apps/api/api/v1.js:1` | `// api.texttocad.dev/v1/*: cadgen's version feed and its telemetry, forwarded to PostHog (src/). vercel.json` |
| telemetry | `apps/api/api/v1.js:5` | `import { missingSettings, posthogStore, settingsOf } from '../src/posthog.mjs';` |
| telemetry | `apps/api/api/v1.js:9` | `const serve = request => handle(request, (store ??= posthogStore(settingsOf(process.env))), {` |
| env-dump | `apps/api/api/v1.js:9` | `const serve = request => handle(request, (store ??= posthogStore(settingsOf(process.env))), {` |
| env-dump | `apps/api/api/v1.js:11` | `missing: missingSettings(process.env),` |
| dependency-file | `apps/api/package.json:0` | `package.json` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:3` | `// Copies the usage analytics cadgen 0.7.7 to 0.7.15 sent before telemetry -- kept in Postgres on Neon by` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:4` | `// the receiver this site ran from 2026-10-02 until api.texttocad.dev forwarded to PostHog -- into` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:5` | `// PostHog, so the Neon database can be deleted.` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:9` | `// `rowsOf` and `propertiesOf` (src/events.mjs, posthog.mjs). So a tool's calls are `tool_used`, a` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:12` | `// `migrated: neon`, and gets an id made from what it is, so a rerun sends the same events and PostHog` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:19` | `// When. Deploy Docs from main switches api.texttocad.dev from Neon to PostHog. Until the switch, an` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:20` | `// opt-out from cadgen 0.7.x deletes in Neon; after it, in PostHog. So the copy is made just BEFORE the` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:23` | `// opted out between the copy and the switch is then deleted from PostHog.` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:28` | `//   export POSTHOG_REGION=us POSTHOG_PROJECT_KEY=phc_... POSTHOG_PROJECT_ID=... POSTHOG_PERSONAL_KEY=phx_...` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:29` | `//   M=apps/api/scripts/migrate-neon-to-posthog.mjs` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:38` | `//   4. Who left between the copy and the switch, deleted from PostHog too:` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:42` | `//   5. In PostHog, the events filtered by `migrated = neon` add up to the dry run's counts. Then delete the` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:51` | `import { EVENTS, posthogStore, propertiesOf, settingsOf } from '../src/posthog.mjs';` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:56` | `const CHUNK = 500; // events a request to PostHog carries` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:103` | `/** The PostHog events one stored batch makes: the receiver's rows and properties, at the time it arrived. */` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:127` | `if (missing.length) throw new Error(`set ${missing.map(name => ({ region: 'POSTHOG_REGION (us or eu)', projectKey: 'POSTHOG_PROJECT_KEY',` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:128` | `personalKey: 'POSTHOG_PERSONAL_KEY', projectId: 'POSTHOG_PROJECT_ID' })[name]).join(', ')}`);` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:154` | `const response = await send(`https://${region}.i.posthog.com/batch/`, {` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:158` | `if (!response.ok) throw new Error(`PostHog answered ${response.status} for events ${start} on: run the import again`);` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:167` | `const store = posthogStore(needs(env, ['region', 'personalKey', 'projectId']), { fetch: send });` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:169` | `log(`  deleted from PostHog: ${gone.length}`);` |
| telemetry | `apps/api/scripts/migrate-neon-to-posthog.mjs:183` | `console.error(`migrate-neon-to-posthog: ${error.message}`);` |
| telemetry | `apps/api/src/events.mjs:2` | `* What cadgen sends (`cadgen/analytics.py`), checked field by field and turned into rows. Every schema a` |
| telemetry | `apps/api/src/events.mjs:52` | `// A crash's frame, as cadgen names one (`cadgen/analytics.py`: `signature`; a page's: core's `crashOf`).` |
| telemetry | `apps/api/src/events.mjs:72` | `// Why a CAD tool's call failed (`cadgen/analytics.py`: `FAILURES`): the caller's, the view's, the machine's or` |
| telemetry | `apps/api/src/events.mjs:76` | `// Why a build failed (`cadgen/analytics.py`: `BUILD_FAILURES`), from what the error was and whose code raised it:` |
| telemetry | `apps/api/src/handler.mjs:3` | `* cadgen's telemetry is sent to -- served by this project's one function (`api/v1.js`, which vercel.json` |
| telemetry | `apps/api/src/handler.mjs:4` | `* sends every /v1 path to). A plain fetch handler over a `store` (PostHog's, posthog.mjs), so the host it runs on and` |
| telemetry | `apps/api/src/handler.mjs:11` | `*   GET    /v1/health          -> 200, or 503 naming a missing setting (posthog.mjs: SETTINGS)` |
| telemetry | `apps/api/src/handler.mjs:12` | `*                              or PostHog's status when it will not take the project's keys` |
| telemetry | `apps/api/src/handler.mjs:59` | `console.warn(`telemetry ${ENDPOINTS.has(path) ? path : 'request'} refused ${status}: ${reason}${senderOf(batch)}`);` |
| telemetry | `apps/api/src/handler.mjs:86` | `// and serves on while PyPI or the function fails. It asks no telemetry service, so it answers even when` |
| telemetry | `apps/api/src/handler.mjs:87` | `// telemetry cannot. With no feed at all, a 503 the edge keeps nowhere.` |
| telemetry | `apps/api/src/handler.mjs:112` | `if (dropped.size) console.info(`telemetry dropped ${[...dropped].map(([name, n]) => `${name} ${n}`).join(', ')}${senderOf(batch)}`);` |
| telemetry | `apps/api/src/handler.mjs:127` | `console.error('telemetry request failed:', codeOf(error));` |
| telemetry | `apps/api/src/handler.test.mjs:7` | `// What cadgen/analytics.py sends from the CAD app...` |
| telemetry | `apps/api/src/handler.test.mjs:209` | `const down = { ...memory(), async insert() { throw Object.assign(new Error('PostHog answered 503'), { code: 'posthog_503' }); } };` |
| telemetry | `apps/api/src/handler.test.mjs:305` | `'telemetry /v1/events refused 400: events[1].calls counts nothing (schema 3, cadgen 0.8.0)',` |
| telemetry | `apps/api/src/handler.test.mjs:306` | `'telemetry /v1/events refused 400: unknown field next_thing (schema 3, cadgen 0.9.1)',` |
| telemetry | `apps/api/src/handler.test.mjs:307` | `'telemetry /v1/events refused 400: the body is not JSON',` |
| telemetry | `apps/api/src/handler.test.mjs:308` | `'telemetry /v1/forget refused 400: not an install id',` |
| telemetry | `apps/api/src/handler.test.mjs:309` | `'telemetry /v1/events refused 403: not from a browser',` |
| telemetry | `apps/api/src/handler.test.mjs:338` | `assert.ok(lines.warn.includes('telemetry request refused 415: the body must be application/json'));` |
| telemetry | `apps/api/src/handler.test.mjs:346` | `[Object.assign(new Error('PostHog answered 503 for 8c347ec3-1342-4db5-a19a-491cbc8c59be'), { code: 'posthog_503' }), 'posthog_503'],` |
| telemetry | `apps/api/src/handler.test.mjs:354` | `assert.deepEqual(lines.error, [`telemetry request failed: ${name}`]);` |
| telemetry | `apps/api/src/handler.test.mjs:380` | `const unset = await handle(new Request('https://api.texttocad.dev/v1/health'), memory(), { missing: ['POSTHOG_PROJECT_KEY'] });` |
| telemetry | `apps/api/src/handler.test.mjs:381` | `assert.deepEqual([unset.status, await unset.json()], [503, { ok: false, missing: ['POSTHOG_PROJECT_KEY'] }]);` |
| telemetry | `apps/api/src/handler.test.mjs:382` | `// A personal key PostHog no longer takes.` |
| telemetry | `apps/api/src/handler.test.mjs:383` | `const refused = { ...memory(), async ready() { throw Object.assign(new Error('PostHog answered 401'), { code: 'posthog_401' }); } };` |
| telemetry | `apps/api/src/handler.test.mjs:385` | `assert.deepEqual([reply.status, await reply.json()], [503, { ok: false, error: 'posthog_401' }]);` |
| telemetry | `apps/api/src/handler.test.mjs:388` | `test('the version feed is the same for everyone, kept at the edge, and answers without the telemetry service', async () => {` |
| telemetry | `apps/api/src/handler.test.mjs:391` | `const reply = await handle(new Request('https://api.texttocad.dev/v1/versions/'), down, { versions: async () => feed, missing: ['POSTHOG_REG` |
| telemetry | `apps/api/src/neon-migration.test.mjs:1` | `// ONE-OFF, with ../scripts/migrate-neon-to-posthog.mjs: delete both once the migration has run.` |
| telemetry | `apps/api/src/neon-migration.test.mjs:5` | `import { batchesOf, COLUMNS, eventsOf, goneInstalls, sql } from '../scripts/migrate-neon-to-posthog.mjs';` |
| telemetry | `apps/api/src/neon-migration.test.mjs:7` | `import { EVENTS, propertiesOf } from './posthog.mjs';` |
| telemetry | `apps/api/src/noise.mjs:2` | `* Crash reports that are never cadgen's bug, dropped before they reach PostHog (README.md, "Never cadgen's` |
| telemetry | `apps/api/src/noise.mjs:8` | `* because it is frequent -- and in the same change the client stops sending it (`cadgen/analytics.py`:` |
| telemetry | `apps/api/src/noise.test.mjs:9` | `// Each signature on the drop list, as released clients sent it to PostHog.` |
| telemetry | `apps/api/src/noise.test.mjs:32` | `// cadgen's bugs, which look like noise in one way or another: every one goes on to PostHog.` |
| telemetry | `apps/api/src/noise.test.mjs:95` | `// Nothing but noise: taken, and nothing for PostHog.` |
| telemetry | `apps/api/src/noise.test.mjs:102` | `'telemetry dropped page_left 4 (schema 3, cadgen 0.7.17)',` |
| telemetry | `apps/api/src/noise.test.mjs:103` | `'telemetry dropped worker_stopped 1 (schema 3, cadgen 0.7.17)',` |
| telemetry | `apps/api/src/posthog.mjs:2` | `* The store over PostHog (cadgen's telemetry: usage counts now, crash reports to come). Every row a batch` |
| telemetry | `apps/api/src/posthog.mjs:3` | `* makes (`events.mjs`) becomes one PostHog event (`EVENTS`), with the install id as its distinct id, the` |
| telemetry | `apps/api/src/posthog.mjs:5` | `* them: never the IP address, nor anything finer. PostHog's own lookup of where an event came from is off` |
| telemetry | `apps/api/src/posthog.mjs:10` | `* An opt-out deletes the install's person and every event under its id (`/forget`): PostHog does that in the` |
| telemetry | `apps/api/src/posthog.mjs:11` | `* background, so what "deleted" means is "queued for deletion". Retention is PostHog's: events go after the` |
| telemetry | `apps/api/src/posthog.mjs:21` | `// PostHog's name for each kind of row, as a product reads them.` |
| telemetry | `apps/api/src/posthog.mjs:31` | `export const SETTINGS = ['POSTHOG_REGION', 'POSTHOG_PROJECT_KEY', 'POSTHOG_PERSONAL_KEY', 'POSTHOG_PROJECT_ID'];` |
| telemetry | `apps/api/src/posthog.mjs:33` | `const TIMEOUT_MS = 8000; // well inside a function's own limit: a PostHog that hangs is a failure, and the batch waits` |
| telemetry | `apps/api/src/posthog.mjs:35` | `/** The settings a host lacks, by name -- missing, or not what PostHog would take (health says so). */` |
| telemetry | `apps/api/src/posthog.mjs:38` | `POSTHOG_REGION: value => REGIONS.has(value),` |
| telemetry | `apps/api/src/posthog.mjs:39` | `POSTHOG_PROJECT_ID: value => /^\d+$/.test(value ?? ''),` |
| telemetry | `apps/api/src/posthog.mjs:46` | `return { region: env.POSTHOG_REGION, projectKey: env.POSTHOG_PROJECT_KEY, personalKey: env.POSTHOG_PERSONAL_KEY,` |
| telemetry | `apps/api/src/posthog.mjs:47` | `projectId: env.POSTHOG_PROJECT_ID };` |
| telemetry | `apps/api/src/posthog.mjs:54` | `* A crash as PostHog's error tracking reads one (`$exception_list`): its type, a value that is only ever` |
| telemetry | `apps/api/src/posthog.mjs:63` | `// PostHog resolves a page's frame through the source map the release uploaded under this id.` |
| telemetry | `apps/api/src/posthog.mjs:74` | `/** A row as PostHog properties: its context, its own fields, and where it came from; nothing unset. */` |
| telemetry | `apps/api/src/posthog.mjs:76` | `// The session twice: `session`, which the counts are read by, and PostHog's own `$session_id`, which error` |
| telemetry | `apps/api/src/posthog.mjs:77` | `// tracking counts an issue's sessions by. A process's id is a UUIDv4, not the v7 PostHog's sessions table` |
| telemetry | `apps/api/src/posthog.mjs:88` | `* A row as one PostHog event. A row with an id (schema 5's, `events.mjs`: `idOf`) is sent under it as the event's` |
| telemetry | `apps/api/src/posthog.mjs:89` | `* `uuid`, and at its batch's time (`at`, the sender's clock): PostHog takes events with the same uuid, event,` |
| telemetry | `apps/api/src/posthog.mjs:92` | `* schema's row PostHog stamps as it arrives.` |
| telemetry | `apps/api/src/posthog.mjs:105` | `export function posthogStore({ region, projectKey, personalKey, projectId }, { fetch: send = fetch } = {}) {` |
| telemetry | `apps/api/src/posthog.mjs:106` | `const capture = `https://${region}.i.posthog.com`;` |
| telemetry | `apps/api/src/posthog.mjs:107` | `const api = `https://${region}.posthog.com/api/projects/${projectId}`;` |
| telemetry | `apps/api/src/posthog.mjs:109` | `// the deletion it owes, and ask again. PostHog's answer is named by its status alone.` |
| telemetry | `apps/api/src/posthog.mjs:112` | `if (!response.ok) throw Object.assign(new Error(`PostHog answered ${response.status}`), { code: `posthog_${response.status}` });` |
| telemetry | `apps/api/src/posthog.mjs:132` | `// put every batch there; one PostHog does not know would lose them all, unseen until someone looked.` |
| telemetry | `apps/api/src/posthog.mjs:136` | `throw Object.assign(new Error("POSTHOG_PROJECT_KEY is not this project's"), { code: 'posthog_project_key' });` |
| telemetry | `apps/api/src/posthog.test.mjs:4` | `import { EVENTS, missingSettings, posthogStore, SETTINGS, settingsOf } from './posthog.mjs';` |
| telemetry | `apps/api/src/posthog.test.mjs:8` | `// What cadgen sends (cadgen/analytics.py): the CAD app's counts, and the build daemon's.` |
| telemetry | `apps/api/src/posthog.test.mjs:30` | `// PostHog over a fetch that keeps what it was asked and answers `status`.` |
| telemetry | `apps/api/src/posthog.test.mjs:31` | `function posthog(status = 200) {` |
| telemetry | `apps/api/src/posthog.test.mjs:37` | `return { asked, store: posthogStore(SETTINGS_EU, { fetch }) };` |
| telemetry | `apps/api/src/posthog.test.mjs:40` | `test("each of a batch's rows is one PostHog event, under the install id, with the country and no location lookup", async () => {` |
| telemetry | `apps/api/src/posthog.test.mjs:41` | `const { asked, store } = posthog();` |
| telemetry | `apps/api/src/posthog.test.mjs:44` | `assert.deepEqual([url, method, body.api_key], ['https://eu.i.posthog.com/batch/', 'POST', 'phc_project']);` |
| telemetry | `apps/api/src/posthog.test.mjs:56` | `test("the build daemon's counts are PostHog events of their own, each a window's to add up", async () => {` |
| telemetry | `apps/api/src/posthog.test.mjs:57` | `const { asked, store } = posthog();` |
| telemetry | `apps/api/src/posthog.test.mjs:67` | `// Schemas before 5 name no batch: PostHog makes up each event's uuid and stamps it as it arrives, as ever.` |
| telemetry | `apps/api/src/posthog.test.mjs:82` | `const { asked, store } = posthog(200);` |
| telemetry | `apps/api/src/posthog.test.mjs:86` | `test("why builds and snapshots failed are PostHog's build_failed and snapshot_failed, by format and reason", async () => {` |
| telemetry | `apps/api/src/posthog.test.mjs:95` | `test('a batch sent again is the same PostHog events, uuid and time alike, so PostHog counts it once', async () => {` |
| telemetry | `apps/api/src/posthog.test.mjs:114` | `test("why a tool's calls failed is PostHog's tool_failed, by tool and reason, to break down and add up", async () => {` |
| telemetry | `apps/api/src/posthog.test.mjs:115` | `const { asked, store } = posthog();` |
| telemetry | `apps/api/src/posthog.test.mjs:124` | `test("a crash is PostHog's $exception: its type and frames, only cadgen's in the app, and no message", async () => {` |
| telemetry | `apps/api/src/posthog.test.mjs:125` | `const { asked, store } = posthog();` |
| telemetry | `apps/api/src/posthog.test.mjs:151` | `// A page's frame names its chunk, by which PostHog finds the source map the release uploaded.` |
| telemetry | `apps/api/src/posthog.test.mjs:158` | `const { asked, store } = posthog();` |
| telemetry | `apps/api/src/posthog.test.mjs:174` | `const { asked, store } = posthog();` |
| telemetry | `apps/api/src/posthog.test.mjs:177` | `url: 'https://eu.posthog.com/api/projects/1234/persons/bulk_delete/', method: 'POST',` |
| telemetry | `apps/api/src/posthog.test.mjs:183` | `test("PostHog refusing or failing is the receiver's failure, named by its status alone", async () => {` |
| telemetry | `apps/api/src/posthog.test.mjs:185` | `const { store } = posthog(status);` |
| telemetry | `apps/api/src/posthog.test.mjs:186` | `await assert.rejects(store.insert(rowsOf(BATCH), { country: 'DE' }), { code: `posthog_${status}` });` |
| telemetry | `apps/api/src/posthog.test.mjs:187` | `await assert.rejects(store.forget(INSTALL), { code: `posthog_${status}` });` |
| telemetry | `apps/api/src/posthog.test.mjs:188` | `await assert.rejects(store.ready(), { code: `posthog_${status}` });` |
| telemetry | `apps/api/src/posthog.test.mjs:193` | `const { asked, store } = posthog();` |
| telemetry | `apps/api/src/posthog.test.mjs:196` | `[['https://eu.posthog.com/api/projects/1234/', 'GET', { authorization: 'Bearer phx_personal' }]]);` |
| telemetry | `apps/api/src/posthog.test.mjs:197` | `const project = token => posthogStore(SETTINGS_EU, { fetch: async () => new Response(JSON.stringify({ api_token: token })) });` |
| telemetry | `apps/api/src/posthog.test.mjs:199` | `await assert.rejects(project('phc_another').ready(), { code: 'posthog_project_key' });` |
| telemetry | `apps/api/src/posthog.test.mjs:202` | `test('the host names its settings, and health names any missing or not what PostHog takes', () => {` |
| telemetry | `apps/api/src/posthog.test.mjs:203` | `const env = { POSTHOG_REGION: 'us', POSTHOG_PROJECT_KEY: 'phc_project', POSTHOG_PERSONAL_KEY: 'phx_personal', POSTHOG_PROJECT_ID: '42' };` |
| telemetry | `apps/api/src/posthog.test.mjs:207` | `assert.deepEqual(missingSettings({ ...env, POSTHOG_REGION: 'asia', POSTHOG_PROJECT_ID: 'my-project' }), ['POSTHOG_REGION', 'POSTHOG_PROJECT_` |
| network | `apps/api/src/versions.mjs:50` | `const response = await fetch(INDEX, {` |
| telemetry | `apps/docs/README.md:137` | `sentence says what text-to-cad sends and how to turn it off, with the privacy policy (`telemetryNote`:` |
| telemetry | `apps/docs/README.md:167` | `cadgen's version feed and its telemetry receiver are their own Vercel project:` |
| dependency-file | `apps/docs/package.json:0` | `package.json` |
| subprocess | `apps/docs/scripts/sync-hero-step-assets.mjs:19` | `import { execFileSync } from "node:child_process";` |
| telemetry | `apps/docs/src/app/llms.txt/route.ts:10` | `telemetryNote,` |
| telemetry | `apps/docs/src/app/llms.txt/route.ts:34` | ``${telemetryNote} See the [privacy policy](${absoluteUrl("/privacy-policy")}).`,` |
| telemetry | `apps/docs/src/app/page.tsx:21` | `telemetryNote,` |
| telemetry | `apps/docs/src/app/page.tsx:60` | `function TelemetryNote() {` |
| telemetry | `apps/docs/src/app/page.tsx:63` | `{telemetryNote.split("`").map((part, index) =>` |
| telemetry | `apps/docs/src/app/page.tsx:312` | `<TelemetryNote />` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:7` | `"How Thompson Labs LLC handles personal data for text-to-cad: what is collected, including cadgen's telemetry (usage counts and crash report` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:32` | `<strong>Telemetry: usage counts and crash reports, when it is on.</strong> cadgen’s` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:85` | `finer than the country. Nothing is sent while cadgen sits unused. Telemetry never includes` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:91` | `Section 5 says when telemetry is on and how to turn it off.` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:128` | `Telemetry: only to understand, in aggregate, how many people use text-to-cad and how` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:145` | `and processes their requests for us, and <strong>PostHog, Inc.</strong>, which stores and` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:146` | `analyzes telemetry for us. PostHog never sees your IP address: only our server sends it` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:147` | `telemetry, with the country it worked out and PostHog’s own location lookup turned off.` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:174` | `Telemetry is kept by PostHog for as long as our plan with it keeps events, currently one` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:177` | `telemetry with those logs. The one exception is a batch our server refuses as malformed:` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:179` | `never your install ID or any other value from it. Turning telemetry off deletes everything stored under your` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:180` | `install ID; PostHog carries the deletion out in the background, which can take some days.` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:194` | `<strong>Telemetry is on once cadgen has told you.</strong> The first <code>cadgen</code>{" "}` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:199` | `<code>telemetry</code> setting in cadgen’s settings file, through restarts and updates, and` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:200` | `one choice counts for every part of cadgen; a no stays a no. Turning telemetry off also turns` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:204` | `of cadgen sends them; turning telemetry off deletes those files too.` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:207` | `To turn telemetry off, run <code>uvx cadgen telemetry off</code>, use{" "}` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:209` | `at the top left, over any open model), or ask your agent to turn off CAD telemetry.` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:212` | `the two. <code>uvx cadgen telemetry on</code> turns it on, and{" "}` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:213` | `<code>uvx cadgen telemetry status</code> shows the setting and your install ID.` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:216` | `Setting <code>DO_NOT_TRACK=1</code> or <code>CADGEN_TELEMETRY=0</code> where cadgen runs` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:218` | `telemetry off for that process and the models it asks cadgen’s build daemon to build,` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:219` | `whatever your setting says; <code>CADGEN_TELEMETRY=1</code> turns it on for that process` |
| telemetry | `apps/docs/src/app/privacy-policy/page.tsx:225` | `Setting <code>CADGEN_UPDATE_CHECK=0</code> where cadgen runs turns the daily version check` |
| network | `apps/docs/src/components/site-header.tsx:30` | `const response = await fetch(GITHUB_REPO_API_URL, {` |
| telemetry | `apps/docs/src/lib/content.ts:27` | `export const telemetryNote =` |
| telemetry | `apps/docs/src/lib/content.ts:28` | `"By default, text-to-cad sends usage stats and crash reports, tagged with a random ID and never including your files, paths or prompts; turn` |
| telemetry | `apps/mcp/README.md:90` | `nothing about the person (`CADGEN_UPDATE_CHECK=0` turns it off; never in CI or from` |
| telemetry | `apps/mcp/README.md:111` | `Marketplace) is left to its store, and Gemini's extension to Gemini. The telemetry: the server` |
| telemetry | `apps/mcp/README.md:115` | `and sends the counts at most every five minutes (`cadgen/analytics.py`): never a path,` |
| telemetry | `apps/mcp/README.md:121` | `release uploads to PostHog), leading into the shared packages' own source, whose modules` |
| telemetry | `apps/mcp/README.md:130` | `counts; it decides nothing there. The agent's `cad_telemetry` reports the` |
| telemetry | `apps/mcp/README.md:163` | `over its own model library and analytics. Everything the page asks of the` |
| dependency-file | `apps/mcp/package.json:0` | `package.json` |
| subprocess | `apps/mcp/scripts/run-tests.mjs:2` | `import { spawnSync } from "node:child_process";` |
| subprocess | `apps/mcp/scripts/run-tests.mjs:24` | `const result = spawnSync(process.execPath, [vitest, "run", "--config", path.join(appRoot, "vitest.config.mjs"), ...process.argv.slice(2)], {` |
| telemetry | `apps/mcp/src/App.test.tsx:297` | `// cadgen's telemetry is on by default once a `cadgen` command has said so: the page never asks.` |
| telemetry | `apps/mcp/src/App.test.tsx:326` | `// DO_NOT_TRACK: the setting says so, and cannot be changed here.` |
| telemetry | `apps/mcp/src/App.test.tsx:331` | `expect(viewer.props!.appSettings![0]).toEqual(expect.objectContaining({ disabled: true, label: 'Telemetry (set by your environment)' }));` |
| telemetry | `apps/mcp/src/App.tsx:203` | `// The usage stats cadgen sends (its telemetry), the same as the browser viewer's: nothing asks here (a` |
| telemetry | `apps/mcp/src/ModelView.tsx:55` | `/** This app's on/off settings, in the app menu: analytics. */` |
| telemetry | `apps/mcp/src/ModelView.tsx:124` | `// A Quick Edit copied, queued or sent, counted by the CAD app's server for its telemetry.` |
| subprocess | `apps/mcp/src/build.test.ts:3` | `import { execFileSync } from 'node:child_process';` |
| telemetry | `apps/mcp/src/main.tsx:14` | `// app's server for its telemetry (`cadgen/analytics.py`), each once a page and never its message.` |
| telemetry | `apps/mcp/vite.config.mjs:54` | `// map (`dist/sourcemaps`, scripts/release/sourcemaps.py), so PostHog can show the source -- the` |
| telemetry | `apps/web/README.md:308` | `### Usage stats (telemetry)` |
| telemetry | `apps/web/README.md:310` | `cadgen's usage stats (`cadgen/analytics.py`) are on by default once a `cadgen` command has said` |
| telemetry | `apps/web/README.md:322` | `leaves the maps out and a release uploads them to PostHog, and the page` |
| telemetry | `apps/web/docs/backend.md:206` | `/ `POST /__cad/analytics/activity` / What the page did, for telemetry: `{touched: true}`, a person touched it; `{quickEdit: true}`, a Quick ` |
| dependency-file | `apps/web/package.json:0` | `package.json` |
| subprocess | `apps/web/scripts/run-tests.mjs:2` | `import { spawnSync } from "node:child_process";` |
| subprocess | `apps/web/scripts/run-tests.mjs:39` | `const result = spawnSync(process.execPath, [` |
| telemetry | `apps/web/src/App.test.mjs:106` | `// CAD's telemetry, as the CAD app's: the consent read once, its answer in the app menu. (The` |
| telemetry | `apps/web/src/App.test.mjs:114` | `// The app menu: Analytics.` |
| telemetry | `apps/web/src/App.test.mjs:116` | `[['Telemetry', false]]);` |
| telemetry | `apps/web/src/App.tsx:99` | `// The usage stats cadgen sends (its telemetry), the same as the CAD app's: nothing asks here (a` |
| telemetry | `apps/web/src/App.tsx:123` | `// A Quick Edit copied, counted by this Viewer's server for its telemetry, as a touch is.` |
| network | `apps/web/src/host/clipboard.ts:34` | `const response = await fetch('/__cad/clipboard', { method: 'POST', headers: { 'x-cadgen-viewer': '1', 'content-type': 'image/png' }, body: p` |
| subprocess | `apps/web/src/host/viewerLinks.test.mjs:2` | `import { execFileSync } from 'node:child_process';` |
| telemetry | `apps/web/src/main.tsx:34` | `// Viewer's server for its telemetry (`cadgen/analytics.py`), each once a page and never its message.` |
| subprocess | `apps/web/vite.config.mjs:1` | `import { spawn } from "node:child_process";` |
| subprocess | `apps/web/vite.config.mjs:95` | `const child = spawn(` |
| telemetry | `apps/web/vite.config.mjs:192` | `// the release uploads every chunk with its source map (scripts/release/sourcemaps.py) for PostHog to` |
| dependency-file | `package.json:0` | `package.json` |
| telemetry | `packages/cadgen/README.md:358` | `and page. Its own requests are two: telemetry` |
| telemetry | `packages/cadgen/README.md:359` | `(`analytics.py`, usage counts under a random id, sent by default once a `cadgen`` |
| telemetry | `packages/cadgen/README.md:368` | `(`analytics.spool`). A process that exits sends nothing either: its last batch --` |
| telemetry | `packages/cadgen/README.md:371` | `(`analytics.KEPT`). One wait remains, bounded, for something only the network can` |
| telemetry | `packages/cadgen/README.md:372` | `do: `cadgen telemetry off`, which waits for the deletion it asks for (still owed,` |
| telemetry | `packages/cadgen/README.md:403` | `analytics.py           # telemetry: usage counts and crash reports (a` |
| telemetry | `packages/cadgen/README.md:407` | `#   answer: settings.json's `telemetry` section)` |
| telemetry | `packages/cadgen/README.md:420` | `#   worker, client, transport, telemetry (what it` |
| dependency-file | `packages/cadgen/pyproject.toml:0` | `pyproject.toml` |
| telemetry | `packages/cadgen/src/cadgen/_internal/api.py:3` | `Two things use it: telemetry (``cadgen/analytics.py``: ``/events`` and ``/forget``) and the daily` |
| telemetry | `packages/cadgen/src/cadgen/_internal/channel.py:24` | `cadgen reads a channel as a token and nothing more: telemetry reports it, and nothing decides by` |
| telemetry | `packages/cadgen/src/cadgen/_internal/channel.py:26` | `a checkout by path), which hears of no release and sends no telemetry by default. A process of an` |
| telemetry | `packages/cadgen/src/cadgen/_internal/cli_from_function.py:422` | `raised on purpose, is also a crash telemetry reports (``cadgen.analytics.report``):` |
| telemetry | `packages/cadgen/src/cadgen/_internal/cli_from_function.py:425` | `(``cadgen.analytics.build_failure``), for the build's count (``cadgen.daemon.telemetry.job_failed``).` |
| telemetry | `packages/cadgen/src/cadgen/_internal/cli_from_function.py:442` | `from cadgen.daemon import telemetry` |
| telemetry | `packages/cadgen/src/cadgen/_internal/cli_from_function.py:444` | `building = bool(os.environ.get("CADGEN_DAEMON_CHILD")) or telemetry.building()` |
| telemetry | `packages/cadgen/src/cadgen/_internal/cli_from_function.py:445` | `analytics.report(exc, "build" if building else "command", bugs_only=True)` |
| telemetry | `packages/cadgen/src/cadgen/_internal/cli_from_function.py:446` | `if telemetry.building():` |
| telemetry | `packages/cadgen/src/cadgen/_internal/cli_from_function.py:447` | `telemetry.job_failed(analytics.build_failure(exc))` |
| telemetry | `packages/cadgen/src/cadgen/_internal/cli_from_function.py:477` | `from cadgen.daemon import telemetry` |
| telemetry | `packages/cadgen/src/cadgen/_internal/cli_from_function.py:479` | `telemetry.job_result(result)  # in a build worker: whether what it made was the store's already` |
| network | `packages/cadgen/src/cadgen/_internal/editable.py:41` | `from urllib.request import url2pathname` |
| telemetry | `packages/cadgen/src/cadgen/_internal/generation.py:1435` | `from cadgen.daemon.telemetry import job_reused` |
| telemetry | `packages/cadgen/src/cadgen/_internal/generation.py:1438` | `job_reused(outcome in ("current", "skipped-peer"))  # in a build worker: telemetry's cache hit, or not` |
| telemetry | `packages/cadgen/src/cadgen/_internal/generation.py:1507` | `from cadgen.daemon.telemetry import job_reused` |
| telemetry | `packages/cadgen/src/cadgen/_internal/generation.py:1588` | `from cadgen.daemon.telemetry import job_reused` |
| telemetry | `packages/cadgen/src/cadgen/_internal/generation.py:1590` | `job_reused(outcome in ("current", "skipped-peer"))  # in a build worker: telemetry's cache hit, or not` |
| eval-exec | `packages/cadgen/src/cadgen/_internal/generation_runner.py:154` | `exec(source_code, module.__dict__)` |
| subprocess | `packages/cadgen/src/cadgen/_internal/mesh_export.py:141` | `proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")` |
| env-dump | `packages/cadgen/src/cadgen/_internal/node_runtime.py:204` | `env = dict(os.environ)` |
| subprocess | `packages/cadgen/src/cadgen/_internal/node_runtime.py:354` | `proc = subprocess.Popen(  # noqa: S603 - argv is fully constructed, never shell-parsed` |
| subprocess | `packages/cadgen/src/cadgen/_internal/picker.py:101` | `done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT_SECONDS, env={**os.environ, **extra})` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:1` | `"""cadgen's telemetry: usage counts and crash reports from the processes that do CAD's work --` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:63` | `1. The environment: ``DO_NOT_TRACK=1`` or ``CADGEN_TELEMETRY=0`` turns it off,` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:64` | ```CADGEN_TELEMETRY=1`` on, over the person's choice -- for the process it is set in, and the builds that process asks of the` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:67` | `2. The person's choice, kept as the ``telemetry`` section of their settings (``cadgen/settings.py``:` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:69` | ```cadgen telemetry on/off``, or the agent's ``cad_telemetry`` (off only). A yes sends all of` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:81` | `Before telemetry, cadgen 0.7.7 to 0.7.15 kept these answers as ``analytics`` (the settings section,` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:94` | `Telemetry never gets in the way of CAD:` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:158` | `f"prompts. Turn off: uvx cadgen telemetry off · {PRIVACY_URL}")` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:160` | `NOTICE_ENV = "CADGEN_TELEMETRY_NOTICE"` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:171` | `SPOOL = "telemetry-spool.jsonl"` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:175` | `KEPT = "telemetry-batches.jsonl"` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:333` | `SECTION = "telemetry"  # this module's part of the settings file` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:339` | `"""The telemetry section, or ``None`` when the settings are there but cannot be read now."""` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:343` | `LOG.debug("could not read the telemetry choice in %s", path, exc_info=True)` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:380` | `"""Change the telemetry section under the settings lock: what is kept, or ``None`` when it` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:385` | `LOG.debug("could not keep the telemetry choice in %s", path, exc_info=True)` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:392` | `ENVIRONMENT = ("DO_NOT_TRACK", "CADGEN_TELEMETRY")` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:397` | `if str(env.get("DO_NOT_TRACK") or "").strip().lower() in _ON:` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:399` | `value = str(env.get("CADGEN_TELEMETRY") or "").strip().lower()` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:404` | `"""``env`` without its telemetry switches (``ENVIRONMENT``), for a process started here that outlives` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:412` | `telemetry off: what is counted for it is never noted, whatever the process that counts was told."""` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:416` | `LOG.debug("could not read a telemetry environment", exc_info=True)` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:622` | `LOG.debug("telemetry notice failed", exc_info=True)` |
| network | `packages/cadgen/src/cadgen/analytics.py:636` | `import urllib.request` |
| network | `packages/cadgen/src/cadgen/analytics.py:639` | `request = urllib.request.Request(url, data=data, method=method,` |
| network | `packages/cadgen/src/cadgen/analytics.py:642` | `with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - http(s) only (`endpoint`)` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:645` | `LOG.debug("telemetry %s %s answered %s", method, url, refusal.code)` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:647` | `except Exception:  # noqa: BLE001 - telemetry never fails anything` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:648` | `LOG.debug("telemetry %s %s failed", method, url, exc_info=True)` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:759` | `"""A crash as telemetry sends it: where it happened (``WHERE``), the error's type, whether the` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:954` | `daemon), or a build worker's job (``cadgen.daemon.telemetry``). With none, it goes to a running` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:1057` | `except Exception:  # noqa: BLE001 - telemetry never fails what it counts` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:1058` | `LOG.debug("telemetry %s failed", method.__name__, exc_info=True)` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:1127` | `# Called as each batch is made, to note what is counted elsewhere (the daemon's pool, ``cadgen.daemon.telemetry``).` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:1479` | `threading.Thread(target=loop, name="cadgen-telemetry", daemon=True).start()` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:1508` | `LOG.debug("telemetry background work failed", exc_info=True)` |
| telemetry | `packages/cadgen/src/cadgen/analytics.py:1510` | `thread = threading.Thread(target=run, name="cadgen-telemetry-once", daemon=True)` |
| telemetry | `packages/cadgen/src/cadgen/authoring.py:829` | `from cadgen.daemon import telemetry` |
| telemetry | `packages/cadgen/src/cadgen/authoring.py:832` | `telemetry.job_child()  # an assembly, for a build this process counts itself (``cold_build``)` |
| telemetry | `packages/cadgen/src/cadgen/authoring.py:911` | `from cadgen.daemon import telemetry` |
| telemetry | `packages/cadgen/src/cadgen/authoring.py:914` | `return telemetry.cold_build(` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:82` | `"telemetry": ("cadgen.cli.telemetry", "show or change the usage stats and crash reports CAD sends: status, on, off"),` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:192` | `"cadgen analytics has been renamed: use cadgen telemetry status/on/off. DO_NOT_TRACK=1 or "` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:193` | `"CADGEN_TELEMETRY=0 in an app's environment turns it off there."` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:255` | `on SIGPIPE -- no traceback, no crash report (``cadgen.analytics.stdout_closed``), nothing more written. Both` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:318` | `# once and before its work, is what those two send by default (`cadgen/analytics.py`).` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:336` | `for telemetry (``cadgen.analytics.report``); the traceback is the person's, as ever."""` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:345` | `# reads; the daemon's supervisor, writing to its own log; and `telemetry`, which says it its own way.` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:346` | `_UNTOLD = frozenset({"mcp", "daemon", "telemetry"})` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:350` | `"""Say, once, what CAD's apps send by default (``cadgen.analytics.notify``): one line on stderr,` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:385` | `from cadgen.daemon import telemetry` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:387` | `return telemetry.cold_build(kind, "command", run)  # no daemon answered it: counted here` |
| telemetry | `packages/cadgen/src/cadgen/cli/__init__.py:392` | `from cadgen.daemon.telemetry import command_kind` |
| telemetry | `packages/cadgen/src/cadgen/cli/doctor.py:63` | `from cadgen.cli.telemetry import describe` |
| subprocess | `packages/cadgen/src/cadgen/cli/doctor.py:108` | `result = subprocess.run(` |
| telemetry | `packages/cadgen/src/cadgen/cli/doctor.py:156` | `# Whether CAD's apps send usage stats, as `cadgen telemetry` says it.` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:1` | `"""``cadgen telemetry`` -- show or change the usage stats and crash reports cadgen sends: from CAD's apps` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:4` | `They are sent by default once a ``cadgen`` command has said so (``cadgen/analytics.py``). ``status`` (the` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:7` | `default does, as the person's own answer, and ``off`` sends nothing. ``DO_NOT_TRACK=1`` or` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:8` | ```CADGEN_TELEMETRY=0`` in a process's environment turns it off for that process, and ``CADGEN_TELEMETRY=1``` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:20` | `DEFAULT_PROG = "cadgen telemetry"` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:23` | `"environment": "set by DO_NOT_TRACK or CADGEN_TELEMETRY in this environment",` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:27` | `"unavailable": "the telemetry setting could not be read",` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:32` | `"""``on`` or ``off``, and why: what ``cadgen telemetry`` and ``cadgen doctor`` say."""` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:66` | `"Telemetry is unchanged; DO_NOT_TRACK=1 in an app's environment keeps it off there.")` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:69` | `print("Telemetry is off; the install id was deleted"` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:76` | `print(f"Telemetry is {describe(found)}.")` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:79` | `"own code failed -- never what they hold: `cadgen telemetry off` turns it off.")` |
| telemetry | `packages/cadgen/src/cadgen/cli/telemetry.py:83` | `print("Note: this environment's DO_NOT_TRACK or CADGEN_TELEMETRY overrides the choice here.")` |
| subprocess | `packages/cadgen/src/cadgen/daemon/artifacts.py:297` | `process = subprocess.Popen([sys.executable, "-P", "-m", "cadgen.daemon.artifacts"],` |
| env-dump | `packages/cadgen/src/cadgen/daemon/artifacts.py:368` | `env = dict(os.environ)` |
| telemetry | `packages/cadgen/src/cadgen/daemon/client.py:72` | `# The telemetry switches (``cadgen.analytics.ENVIRONMENT``) are the client's too: a` |
| telemetry | `packages/cadgen/src/cadgen/daemon/client.py:73` | `# client whose environment turns telemetry off has none of its builds counted, whatever` |
| telemetry | `packages/cadgen/src/cadgen/daemon/client.py:74` | `# the environment of the build that started the daemon said (``cadgen.daemon.telemetry``).` |
| telemetry | `packages/cadgen/src/cadgen/daemon/client.py:83` | `"DO_NOT_TRACK",` |
| telemetry | `packages/cadgen/src/cadgen/daemon/client.py:84` | `"CADGEN_TELEMETRY",` |
| subprocess | `packages/cadgen/src/cadgen/daemon/client.py:468` | `def _reap_detached(process: subprocess.Popen) -> None:` |
| subprocess | `packages/cadgen/src/cadgen/daemon/client.py:487` | `def _spawn_daemon(address: str) -> subprocess.Popen / None:` |
| telemetry | `packages/cadgen/src/cadgen/daemon/client.py:493` | `# daemon serves every client, so it takes no telemetry switch from the one that` |
| subprocess | `packages/cadgen/src/cadgen/daemon/client.py:505` | `return subprocess.Popen(` |
| telemetry | `packages/cadgen/src/cadgen/daemon/client.py:812` | `"""Hand a command's counts to the running daemon, which sends them with its own telemetry` |
| telemetry | `packages/cadgen/src/cadgen/daemon/client.py:813` | `(``cadgen.daemon.telemetry.counted``): a command sends nothing itself. Like ``status`` it` |
| telemetry | `packages/cadgen/src/cadgen/daemon/client.py:815` | `or none running -- they are kept for the next process that sends (``analytics.spool``). One` |
| telemetry | `packages/cadgen/src/cadgen/daemon/client.py:823` | `except Exception:  # noqa: BLE001 - telemetry never fails the command it counts` |
| subprocess | `packages/cadgen/src/cadgen/daemon/executors.py:384` | `process = subprocess.Popen(` |
| subprocess | `packages/cadgen/src/cadgen/daemon/housekeeping.py:168` | `with subprocess.Popen(` |
| subprocess | `packages/cadgen/src/cadgen/daemon/memory.py:58` | `total = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=2))` |
| subprocess | `packages/cadgen/src/cadgen/daemon/memory.py:178` | `output = subprocess.check_output(` |
| telemetry | `packages/cadgen/src/cadgen/daemon/pool.py:128` | `until the daemon's own telemetry has closed (``server.serve``)."""` |
| subprocess | `packages/cadgen/src/cadgen/daemon/pool.py:236` | `output = subprocess.check_output(` |
| subprocess | `packages/cadgen/src/cadgen/daemon/pool.py:300` | `self.proc = subprocess.Popen(` |
| telemetry | `packages/cadgen/src/cadgen/daemon/server.py:44` | `from cadgen.daemon import telemetry, transport` |
| telemetry | `packages/cadgen/src/cadgen/daemon/server.py:412` | `build = None if is_artifact else telemetry.build(request, job)  # counted as it ends, if it is one` |
| telemetry | `packages/cadgen/src/cadgen/daemon/server.py:433` | `telemetry.worker_died(exc.exit_status)  # a worker that could not start` |
| telemetry | `packages/cadgen/src/cadgen/daemon/server.py:509` | `telemetry.exited(frame, build)` |
| telemetry | `packages/cadgen/src/cadgen/daemon/server.py:556` | `telemetry.worker_died(exc.exit_status)` |
| telemetry | `packages/cadgen/src/cadgen/daemon/server.py:614` | `analytics.report(error, "request")  # the daemon's own crash: its recorder's (telemetry.start)` |
| telemetry | `packages/cadgen/src/cadgen/daemon/server.py:719` | `# Read as each batch is made, inside the recorder's guard: nothing telemetry touches can stop the serving.` |
| telemetry | `packages/cadgen/src/cadgen/daemon/server.py:720` | `telemetry.start(lambda: _POOL.snapshot())` |
| telemetry | `packages/cadgen/src/cadgen/daemon/server.py:769` | `telemetry.counted(request)` |
| telemetry | `packages/cadgen/src/cadgen/daemon/server.py:841` | `analytics.report(error, "request", handled=False)` |
| telemetry | `packages/cadgen/src/cadgen/daemon/server.py:849` | `telemetry.close()  # its last batch, kept for the next process to send: a local write, after the address is free` |
| telemetry | `packages/cadgen/src/cadgen/daemon/telemetry.py:1` | `"""The build daemon's telemetry (``cadgen/analytics.py``): the builds it answers and how they end, its` |
| telemetry | `packages/cadgen/src/cadgen/daemon/telemetry.py:11` | `ends in (``cli_from_function.report_failure``: ``analytics.build_failure``), from arguments refused` |
| telemetry | `packages/cadgen/src/cadgen/daemon/telemetry.py:17` | `whose environment turns telemetry off (``analytics.refused``) has nothing it asks for counted.` |
| telemetry | `packages/cadgen/src/cadgen/daemon/telemetry.py:21` | `like a command's counts, or kept for the next process that sends (``analytics.spool``).` |
| telemetry | `packages/cadgen/src/cadgen/daemon/telemetry.py:53` | `except Exception:  # noqa: BLE001 - telemetry never fails what it counts` |
| telemetry | `packages/cadgen/src/cadgen/daemon/telemetry.py:54` | `LOG.debug("daemon telemetry %s failed", method.__name__, exc_info=True)` |
| ... | 812 more | |

## LOW

| rule | file:line | text |
|---|---|---|
| home-write | `CONTRIBUTING.md:184` | `- Codex: its log database, `~/.codex/logs_2.sqlite` (lines starting `MCP server stderr`)` |
| home-write | `README.md:167` | `git clone --depth 1 --branch latest https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad` |
| home-write | `README.md:177` | `git -C ~/.cursor/plugins/local/text-to-cad pull` |
| home-write | `README.md:183` | `rm -rf ~/.cursor/plugins/local/text-to-cad` |
| home-write | `apps/docs/src/lib/content.ts:71` | `"git clone --depth 1 --branch latest https://github.com/earthtojake/text-to-cad ~/.cursor/plugins/local/text-to-cad",` |
| home-write | `apps/docs/src/lib/content.ts:72` | `update: "git -C ~/.cursor/plugins/local/text-to-cad pull",` |
| home-write | `apps/docs/src/lib/content.ts:73` | `remove: "rm -rf ~/.cursor/plugins/local/text-to-cad",` |
| home-write | `docs/migrations/migrating-0.4-to-0.5.md:73` | ``~/.cache/cadgen`. An assembly is a model that imports its part models and calls` |
| home-write | `docs/migrations/migrating-0.4-to-0.5.md:681` | `3. **The old cache.** v0.4's `~/.cache/cadgen` layout (`packages/`,` |
| home-write | `docs/migrations/migrating-0.4-to-0.5.md:687` | `rm -rf ~/.cache/cadgen          # or $CADGEN_CACHE_DIR if you set one` |
| home-write | `docs/migrations/migrating-0.4-to-0.5.md:981` | `/ Derived geometry / In-tree `__cadgen__/models/<entry>/` render packages / `~/.cache/cadgen/objects/` — content-addressed components and tr` |
| home-write | `docs/migrations/migrating-0.4-to-0.5.md:982` | `/ Freshness / Provenance embedded in the STEP text, later a `records/` tier / `~/.cache/cadgen/index/model/<sha256(script path)>` — the mode` |
| home-write | `docs/migrations/migrating-0.4-to-0.5.md:1020` | `platform cache dir (`~/.cache/cadgen` on Linux and macOS) — with two sides:` |
| home-write | `packages/cadgen/README.md:35` | `/ [`STORE.md`](STORE.md) / The store's contract: layout, the two-sides law, tree/record shapes, the gate, invariants, link-vs-component, con` |
| home-write | `packages/cadgen/README.md:81` | ``~/.cache/cadgen` is the store: content-addressed objects (a model's result` |
| home-write | `packages/cadgen/STORE.md:3` | ``~/.cache/cadgen/` — where every model's result lives. Read this before` |
| home-write | `packages/cadgen/STORE.md:37` | `/ **store** / the whole cache, `~/.cache/cadgen/`: `objects/` + `index/` /` |
| home-write | `packages/cadgen/STORE.md:64` | `~/.cache/cadgen/                      (CADGEN_CACHE_DIR overrides; else the platform cache dir)` |
| home-write | `packages/cadgen/STORE.md:1785` | `delete `~/.cache/cadgen` (or the `CADGEN_CACHE_DIR` directory); every model` |
| home-write | `packages/cadgen/src/cadgen/_internal/doors.py:66` | `document = Path(document).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/_internal/doors.py:114` | `path = Path(target).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/_internal/filetrace.py:187` | `names += [os.path.expanduser(name) for name in ("~/Library/Fonts", "~/.fonts", "~/.local/share/fonts")]` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation.py:122` | `step = Path(step_path).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation.py:358` | `if preloaded_scene.step_path != spec.step_path.expanduser().resolve():` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation.py:497` | `preview={"output": str(spec.step_path.expanduser().resolve()), "tree": result_hash},` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation.py:582` | `outputs[str(spec.step_path.expanduser().resolve())] = {"sha256": exported_hash}` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation.py:636` | `key = str(Path(declared.path).expanduser().resolve())` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation.py:750` | `remember_renamed_digest(spec.step_path.expanduser().resolve(), exported_hash, staged_identity)` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation.py:758` | `hashes[str(spec.step_path.expanduser().resolve())] = exported_hash` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation.py:769` | `saved={"output": str(spec.step_path.expanduser().resolve()),` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation.py:1341` | `return str(spec.step_path.expanduser().resolve()) if spec.step_path is not None else None` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation.py:1343` | `return str(export.path.expanduser().resolve())` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation.py:1598` | `"document": str(spec.dxf_path.expanduser().resolve()) if spec.dxf_path is not None else None,` |
| home-write | `packages/cadgen/src/cadgen/_internal/generation_spec.py:107` | `path=path.expanduser().resolve(),` |
| home-write | `packages/cadgen/src/cadgen/_internal/glb_topology.py:87` | `payload = path.expanduser().resolve().read_bytes()` |
| home-write | `packages/cadgen/src/cadgen/_internal/mesh_door.py:69` | `[(fmt, None if out is None else Path(out).expanduser())],` |
| home-write | `packages/cadgen/src/cadgen/_internal/mesh_export.py:239` | `outputs[str(Path(output_path).expanduser().resolve())] = output_entry` |
| home-write | `packages/cadgen/src/cadgen/_internal/mesh_export.py:360` | `entry = (record.get("outputs") or {}).get(str(path.expanduser().resolve()))` |
| home-write | `packages/cadgen/src/cadgen/_internal/node_runtime.py:205` | `root = Path(package_root).expanduser().resolve() if package_root else node_package_root()` |
| home-write | `packages/cadgen/src/cadgen/_internal/node_runtime.py:341` | `script_path = Path(script).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/_internal/picker.py:75` | `return ["kdialog", "--title", "Open", "--getopenfilename", os.path.expanduser("~")], {}, False` |
| home-write | `packages/cadgen/src/cadgen/_internal/source_hash.py:37` | `return PythonSourceHash(source_hash=_sha256_file(script_path.expanduser().resolve()))` |
| home-write | `packages/cadgen/src/cadgen/_internal/source_hash.py:180` | `# (``site.getuserbase()``, ``~/.local`` on posix) holds bin/ and share/ as well, and` |
| home-write | `packages/cadgen/src/cadgen/_internal/source_sidecar.py:551` | `document_resolved = document.expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_hash.py:17` | `with open_with_ladder(step_path.expanduser().resolve(), "rb") as handle:` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_reemit.py:68` | `path = Path(text).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_reemit.py:92` | `text = Path(text).expanduser().read_text(encoding="utf-8")` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_reemit.py:113` | `text = Path(text).expanduser().read_text(encoding="utf-8")` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_reemit.py:151` | `primary = str(out.expanduser().resolve())` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_reemit.py:175` | `destination = Path(out).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_reemit.py:355` | `scene.step_path = out.expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_scene_loader.py:448` | `resolved_step_path = step_path.expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_scene_loader.py:550` | `resolved_step_path = step_path.expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_scene_loader.py:586` | `path.expanduser().resolve(),` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_scene_loader.py:587` | `start=base_dir.expanduser().resolve(),` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_scene_mesh.py:178` | `resolved = Path(step_path).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_scene_package.py:329` | `resolved_step_path = step_path.expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/_internal/step_scene_package.py:372` | `resolved_step_path = step_path.expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/_internal/validation_door.py:87` | `path = Path(value).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/assets.py:106` | `return Path(value).expanduser().resolve() if value else None` |
| home-write | `packages/cadgen/src/cadgen/assets.py:165` | `return Path(explicit).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/cad_ref_syntax.py:121` | `candidate = os.path.expanduser(prefix)` |
| home-write | `packages/cadgen/src/cadgen/catalog.py:153` | `resolved = Path(path).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/catalog.py:254` | `resolved = str(Path(entry_path).expanduser().resolve())` |
| home-write | `packages/cadgen/src/cadgen/catalog.py:347` | `resolved = Path(entry_path).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/catalog.py:380` | `resolved = Path(entry_path).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/cli/_run_model.py:138` | `script = Path(items[0]).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/cli/doctor.py:43` | `base = Path(target).expanduser() if target else Path.cwd()` |
| home-write | `packages/cadgen/src/cadgen/cli/store.py:122` | `path = Path(target).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/cli/urdf_validate.py:60` | `roots[name.strip()] = Path(raw.strip()).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/daemon/housekeeping.py:137` | `resolved = Path(root).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/daemon/housekeeping.py:216` | `key = hashlib.sha256(str(Path(root).expanduser().resolve()).encode("utf-8")).hexdigest()[:16]` |
| home-write | `packages/cadgen/src/cadgen/mcp/browser.py:36` | `process = subprocess.Popen(list(command), cwd=cwd or os.path.expanduser("~"), stdin=subprocess.DEVNULL,` |
| home-write | `packages/cadgen/src/cadgen/mcp/server.py:219` | `path = file_uri_path(value) or os.path.expanduser(value.strip())` |
| home-write | `packages/cadgen/src/cadgen/mcp/ui.py:43` | `return Path(override).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/render.py:31` | `resolved = path.expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/render.py:33` | `return os.path.relpath(resolved, start=base_dir.expanduser().resolve()).replace(os.sep, "/")` |
| home-write | `packages/cadgen/src/cadgen/render.py:39` | `return relative_to_directory(path, owner_path.expanduser().resolve().parent)` |
| home-write | `packages/cadgen/src/cadgen/snapshot_cli.py:306` | `path = (cwd / Path(text).expanduser()).resolve()` |
| home-write | `packages/cadgen/src/cadgen/snapshot_cli.py:412` | `job_path = (cwd / Path(raw_job).expanduser()).resolve()` |
| home-write | `packages/cadgen/src/cadgen/snapshot_cli.py:510` | `raw_path = Path(input_text).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/snapshot_core.py:621` | `display_path = Path(display).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/snapshot_core.py:943` | `candidate = Path(output_path).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/snapshot_video.py:191` | `video_path = Path(video).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/sources.py:31` | `resolved = Path(script_path).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/step_artifact_cli.py:162` | `repo_root = Path(repo_root).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/step_artifact_cli.py:163` | `step_path = Path(step).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/step_export.py:1214` | `output_path = output_path.expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/step_export_target.py:260` | `out = Path(raw).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/step_export_target.py:321` | `repo_root = Path(repo_root).expanduser().resolve() if repo_root else Path.cwd()` |
| home-write | `packages/cadgen/src/cadgen/step_scene.py:31` | `resolved = Path(step_path).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/step_targets.py:119` | `return Path(raw_target).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/step_targets.py:137` | `resolved = path.expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/step_targets.py:175` | `if Path(raw_target).expanduser().suffix.lower() in STEP_SUFFIXES:` |
| home-write | `packages/cadgen/src/cadgen/step_targets.py:195` | `path = Path(target).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/step_topology_artifact.py:221` | `step_path = Path(target.step_path).expanduser().resolve()` |
| home-write | `packages/cadgen/src/cadgen/store/_references.py:395` | `scene = LoadedStepScene(output_path.expanduser().resolve(), [], prototypes, source_kind="python",` |
| home-write | `packages/cadgen/src/cadgen/store/closure.py:968` | `key = str(Path(path).expanduser().resolve())` |
| home-write | `packages/cadgen/src/cadgen/store/forget.py:31` | `path = Path(target).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/store/index.py:26` | `return str(Path(path).expanduser().resolve())` |
| home-write | `packages/cadgen/src/cadgen/store/paths.py:5` | `3. ``~/.cache/cadgen`` otherwise.` |
| home-write | `packages/cadgen/src/cadgen/store/paths.py:43` | `root = Path(override).expanduser()` |
| home-write | `packages/cadgen/src/cadgen/store/paths.py:56` | `return Path.home() / ".cache" / "cadgen"` |
| home-write | `packages/cadgen/src/cadgen/store/records.py:127` | `return str(Path(path).expanduser().resolve())` |
| home-write | `packages/cadgen/src/cadgen/urdf_source.py:1447` | `return (Path(package_root).expanduser() / Path(*mesh_ref.package_path.parts)).resolve()` |
| home-write | `packages/cadgen/src/cadgen/viewer/http_app.py:248` | `return os.path.expanduser("~")` |
| home-write | `packages/cadgen/src/cadgen/viewer/recents.py:71` | `return Path.home() / "Library" / "Application Support" / "cadgen"` |
| home-write | `packages/cadgen/src/cadgen/viewer/recents.py:73` | `return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "cadgen-state"` |
| home-write | `packages/cadgen/src/cadgen/viewer/recents.py:74` | `return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "cadgen"` |
| home-write | `packages/cadgen/src/cadgen/viewer/store_paths.py:48` | `"""``CADGEN_CACHE_DIR``, else the platform convention, else ``~/.cache/cadgen``."""` |
| home-write | `packages/core/src/lib/export/meshExportCli.test.js:57` | `// LOCALAPPDATA (Windows), then os.homedir()/.cache/cadgen. Blanking the first` |
| home-write | `packages/core/src/lib/export/meshExportCli.test.js:59` | `// platform default -- and puts it at <root>/.cache/cadgen on both. os.homedir()` |
| home-write | `packages/core/src/lib/surf/tessellationCacheFs.mjs:32` | `const expanded = override.replace(/^~(?=$/[/\\])/, os.homedir());` |
| home-write | `packages/core/src/lib/surf/tessellationCacheFs.mjs:44` | `return path.join(os.homedir(), ".cache", "cadgen");` |
| home-write | `packages/ui/src/renderers/kit/status/reportIssue.test.js:73` | `"  File \"~/.venv/lib/python3.12/site-packages/cadgen/build.py\", line 9, in build",` |
| home-write | `scripts/bench/cadgen-performance/README.md:36` | `--cadgen-src packages/cadgen/src --node-bin ~/.nvm/versions/node/v22.22.0/bin \` |
| home-write | `scripts/bench/cadgen-performance/agent_edits.py:134` | `parser.add_argument("--store", help="Dedicated CADGEN_CACHE_DIR; never ~/.cache/cadgen")` |
| home-write | `scripts/bench/cadgen-performance/agent_edits.py:160` | `model = Path(args.model).expanduser().resolve()` |
| home-write | `scripts/bench/cadgen-performance/agent_edits.py:161` | `store = Path(args.store).expanduser().resolve()` |
| home-write | `scripts/bench/cadgen-performance/agent_edits.py:162` | `if store == (Path.home() / ".cache/cadgen").resolve():` |
| home-write | `scripts/bench/cadgen-performance/agent_edits.py:168` | `project = Path(args.project).expanduser().resolve()` |
| home-write | `scripts/bench/cadgen-performance/agent_edits.py:182` | `path = Path(getattr(args, f"{kind}_model") or model).expanduser().resolve()` |
| home-write | `scripts/bench/cadgen-performance/agent_edits.py:187` | `comment_path = Path(args.comment_model or edits["leaf"][0]).expanduser().resolve()` |
| home-write | `scripts/bench/cadgen-performance/agent_edits.py:192` | `env.update(PYTHONPATH=str(Path(args.cadgen_src).expanduser().resolve()), CADGEN_CACHE_DIR=str(store),` |
| home-write | `scripts/bench/cadgen-performance/agent_edits.py:193` | `CADGEN_DAEMON_SOCKET=str(Path(args.daemon_socket).expanduser()),` |
| home-write | `scripts/bench/cadgen-performance/agent_edits.py:194` | `CADGEN_DAEMON_STATE_DIR=str(Path(args.daemon_state or store.parent / "daemon").expanduser().resolve()),` |
| home-write | `scripts/bench/cadgen-performance/agent_edits.py:199` | `env["PATH"] = f"{Path(args.node_bin).expanduser().resolve()}{os.pathsep}{env.get('PATH', '')}"` |
| home-write | `scripts/bench/cadgen-performance/common.py:69` | `path = Path(value).expanduser().resolve()` |
| home-write | `scripts/bench/cadgen-performance/warm_build.py:85` | `os.environ.update(CADGEN_DAEMON="1", CADGEN_DAEMON_SOCKET=str(Path(args.child_daemon_socket).expanduser().resolve()))` |
| home-write | `scripts/install/dev_install.py:59` | `CURSOR_PLUGINS = Path.home() / ".cursor" / "plugins" / "local"` |
| home-write | `scripts/install/dev_install.py:159` | `home = Path.home()` |
| home-write | `scripts/install/dev_install.py:200` | `Both write the same ~/.codex, which the app, the terminal CLI and the IDE extension share,` |
| home-write | `scripts/install/dev_install.py:511` | `return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"` |
| home-write | `scripts/install/dev_install.py:513` | `return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json"` |
| home-write | `scripts/install/dev_install.py:514` | `return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"` |
| home-write | `scripts/test/test-python.sh:63` | `# developer's real ~/.cache/cadgen: tests assert exact built/reused counts and` |
| home-write | `skills/cad/references/supported-exports.md:11` | `Native GLB exports are ordinary glTF 2.0 binary files for external tools: Y-up, with one material per distinct part/face color. Do not confu` |
| home-write | `skills/gcode/scripts/orca_presets.py:29` | `home = Path.home()` |
| home-write | `skills/gcode/scripts/orca_presets.py:31` | `Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "OrcaSlicer"]` |
| home-write | `skills/gcode/scripts/orca_presets.py:68` | `path = Path(ref).expanduser()` |
| home-write | `skills/gcode/scripts/orca_presets.py:113` | `out = Path(args.out).expanduser().resolve()` |
| home-write | `tests/python/global/test_skill_self_containment.py:121` | `expanded = os.path.expanduser(local_path)` |
| home-write | `tests/python/global/test_skill_self_containment.py:269` | `return {os.path.expanduser(value) for value in values}` |
| home-write | `tests/python/global/test_skill_self_containment.py:349` | `expanded = os.path.expanduser(lookup_path)` |
| home-write | `tests/python/global/test_tests_are_self_contained.py:13` | `reads the developer's ~/.cache/cadgen (that is a convention, not something this` |
| home-write | `tests/python/packages/cadgen/mcp/test_browser.py:46` | `self.assertEqual(self.started_in(marker), os.path.realpath(os.path.expanduser("~")))` |
| home-write | `tests/python/packages/cadgen/test_package_portability.py:271` | `"home": str(Path.home()),` |
| home-write | `tests/python/packages/cadgen/test_path_semantics.py:69` | `self.assertEqual(doctor._resolve_skill("~/skill"), Path("~/skill").expanduser() / "SKILL.md")` |
| home-write | `tests/python/packages/cadgen/test_telemetry_crashes.py:59` | `for secret in ("secret", "/home/someone", "no such event", os.path.expanduser("~")):` |
| home-write | `tests/python/packages/cadgen/viewer/test_http_layer.py:236` | `self.assertEqual(app.start, os.path.expanduser("~").replace(os.sep, "/"))` |
| home-write | `tests/python/skills/cad/cadgen/test_generation.py:169` | `step_path=step_path.expanduser().resolve(),` |
| home-write | `tests/python/skills/gcode/test_orca_presets.py:41` | `"wall_loops": "2", "compatible_printers_condition": "printer_notes=~/.*ACME.*/"})` |
| home-write | `tests/python/support/cad_test_roots.py:34` | `# The store is content-addressed and shared (~/.cache/cadgen unless` |
