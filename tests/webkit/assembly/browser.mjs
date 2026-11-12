/** Real shared viewer, three distinct snapshots, independent CAD-frame expectations and owned cleanup. */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, writeFile, readFile, readdir } from 'node:fs/promises';
import { chromium, webkit } from '../../site/npm-context.mjs';
import { serveWebkit } from '../webkit-server.mjs';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const encode = value => Buffer.from(JSON.stringify(value));
function cube(origin, size) {
  const vertices = Array.from({ length: 8 }, (_, i) => origin.map((n, axis) => n + (i & (1 << axis) ? size[axis] : 0)));
  const faces = [[0, 2, 1], [1, 2, 3], [4, 5, 6], [5, 7, 6], [0, 1, 4], [1, 5, 4], [2, 6, 3], [3, 6, 7], [0, 4, 2], [2, 4, 6], [1, 3, 5], [3, 7, 5]];
  const bytes = Buffer.alloc(84 + 50 * faces.length); bytes.writeUInt32LE(faces.length, 80);
  faces.forEach((face, i) => face.forEach((vertex, j) => vertices[vertex].forEach((n, k) => bytes.writeFloatLE(n, 84 + 50 * i + 12 + j * 12 + k * 4))));
  return { bytes, bounds: [...origin, ...origin.map((n, i) => n + size[i])] };
}
const routes = new Map([['/favicon.ico',(_,res)=>res.writeHead(204).end()]]), versions = ['v1', 'v2', 'wip'];
for (const [index, version] of [...versions, 'proto'].entries()) {
  const shapes = [cube([0, 0, 0], [40 + index * 10, 30, 8]), cube([8, 8, 8], [5, 5, 20]), cube([28, 8, 8], [5, 5, 20])];
  const names = [version === 'proto' ? 'constructor' : 'base', 'screw#1', 'screw#2'];
  shapes.forEach((shape, i) => routes.set(`/${version}/${i}.stl`, (_, res) => res.end(shape.bytes)));
  const manifest = { title: version, units: 'mm', up: 'z', parts: shapes.map((shape, i) => ({ name: names[i], file: `${i}.stl`, sha256: hash(shape.bytes), bounds_mm: shape.bounds, color: ['#487ca8', '#eaa840', '#eaa840'][i] })) };
  const raw = encode(manifest); routes.set(`/${version}/view.json`, (_, res) => res.end(raw));
  const guide = { schema: 'cad-agent.assembly-guide/1', snapshot: { id: version, revision: version, status: version === 'wip' ? 'wip' : 'released', source_commit: String(index + 1).repeat(40) }, model: { file: 'view.json', sha256: hash(raw) },
    subassemblies: [{ id: 'frame', title: 'Frame', parts: names }], steps: [
      { id: 'base', title: 'Seat base', text: `Instruction ${version}: base only.`, subassembly: 'frame', parts: [names[0]], highlight: [names[0]], offsets_mm: {} },
      { id: 'screws', title: 'Add both screws', text: `Instruction ${version}: fit both screws.`, subassembly: 'frame', parts: names, highlight: names.slice(1), offsets_mm: { 'screw#1': [0, 0, 25 + index * 5], 'screw#2': [0, 0, 25 + index * 5] }, requires: ['base'], camera: { direction: [0.6, -1, -0.35] } },
    ] };
  routes.set(`/${version}/guide.json`, (_, res) => res.end(encode(guide)));
  if (version === 'v1') {
    const framing = structuredClone(guide); framing.model.file = '../v1/view.json';
    framing.steps[1].offsets_mm['screw#1'] = [120, 0, 25];
    routes.set('/framing/guide.json', (_, res) => res.end(encode(framing)));
  }
}
const legacyShape = cube([0, 0, 0], [10, 20, 30]);
routes.set('/legacy/small%20part.stl', (_, res) => res.end(legacyShape.bytes));
routes.set('/legacy/view.json', (_, res) => res.end(encode({ parts: [{ name: 'small part', file: 'small part.stl', color: 'steelblue', bounds_mm: legacyShape.bounds }] })));
// Native source exports are shared with the independent BREP/tool suite, not reconstructed from paths.
const serialRoot = new URL('../../fixtures/assembly-plan/', import.meta.url);
const serialFiles = new Map(await Promise.all((await readdir(serialRoot)).filter(n => /\.(?:json|stl|bin)$/.test(n)).map(async n => [n, await readFile(new URL(n, serialRoot))])));
const serialPlan = JSON.parse(serialFiles.get('plan.json')), serialGuide = JSON.parse(serialFiles.get('guide.json')), serialMini = JSON.parse(serialFiles.get('mini.json'));
assert.equal(serialGuide.assembly_plan.sha256, hash(serialFiles.get('plan.json')));
assert.deepEqual(serialMini.assembly_plan, serialGuide.assembly_plan);
for (const variant of ['serial', 'serial-wrong-axis', 'serial-wrong-order', 'serial-stale']) {
  for (const [name, bytes] of serialFiles) routes.set(`/${variant}/${name}`, (_, res) => res.end(bytes));
  const plan = structuredClone(serialPlan), guide = structuredClone(serialGuide), mini = structuredClone(serialMini);
  if (variant === 'serial-wrong-axis') plan.operations[0].path_mm = [[0,20,25],[0,0,25],[0,0,0]];
  if (variant === 'serial-wrong-order') {
    plan.operations.reverse(); plan.operations[0].requires = []; plan.operations[1].requires = ['lid']; guide.steps.reverse();
  }
  const bytes = variant === 'serial' ? serialFiles.get('plan.json') : encode(plan);
  if (variant !== 'serial-stale') guide.assembly_plan.sha256 = mini.assembly_plan.sha256 = hash(bytes);
  routes.set(`/${variant}/plan.json`, (_, res) => res.end(bytes));
  routes.set(`/${variant}/guide.json`, (_, res) => res.end(encode(guide)));
  routes.set(`/${variant}/mini.json`, (_, res) => res.end(encode(mini)));
  routes.set(`/${variant}/index.html`, (_, res) => {
    res.setHeader('Content-Type','text/html');
    res.end(`<!doctype html><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="/kit/model.css"><style>body{margin:0}cad-model{display:block;width:100%;height:44vh;min-height:230px}</style><script type="module" src="/kit/model.js"></script><cad-model src="/${variant}/mini.json" loading="eager" turn="0"></cad-model><cad-model src="/serial/mini.json" loading="eager" turn="0"></cad-model>`);
  });
}
const engine = process.env.PLAYWRIGHT_BROWSER === 'webkit' ? webkit : chromium;
const out = process.env.TEST_OUTPUT || '/tmp/cad-agent-assembly-guide'; await mkdir(out, { recursive: true });
const site = await serveWebkit(routes); let browser, cors;

const cases = [], errors = [], consoleErrors = [];
const near = (actual, expected, tolerance = 1e-6) => actual.forEach((n, i) => assert.ok(Math.abs(n - expected[i]) < tolerance, `${actual} != ${expected}`));
// Four noncoplanar corners chosen from native source boxes, never from the motion plan.
const serialBoxes = JSON.parse(serialFiles.get('fixture.json')).boxes;
const serialCorners = Object.fromEntries(Object.entries(serialBoxes).map(([name, boxes]) => {
  const b = boxes[0], a = b.slice(0,3); return [name,[a,[a[0]+b[3],a[1],a[2]],[a[0],a[1]+b[4],a[2]],[a[0],a[1],a[2]+b[5]]]];
}));
function serialExpected(position) {
  const p = Math.max(0,Math.min(1,position)), q = Math.max(0,Math.min(1,position-1));
  const plate = p <= 4/9 ? [20-45*p,0,25] : [0,0,45*(1-p)];
  const lid = q <= 7/11 ? [35-55*q,0,20] : [0,0,55*(1-q)];
  return Object.fromEntries(Object.entries(serialCorners).map(([name, points]) => [name,points.map(point => point.map((v,i) => v + (['plate','fastener'].includes(name) ? plate[i] : name === 'lid' ? lid[i] : 0)))]));
}
function checkSerial(actual, position, tolerance = .002) {
  const expected = serialExpected(position);
  for (const [name, points] of Object.entries(expected)) points.forEach((point,i) => point.forEach((n,k) => assert.ok(Math.abs(actual[name][i][k]-n) <= tolerance, `${name} world landmark at ${position}: ${actual[name][i]} != ${point}`)));
}
async function serialBrowserChecks(page, browser) {
  const packet = { sourceRevision:process.env.TEST_SOURCE_REVISION || 'unrecorded', engine:engine.name(), browserVersion:browser.version(),
    sourcePlan:hash(serialFiles.get('plan.json')), fixtureMeshes:Object.fromEntries([...serialFiles].filter(([n])=>n.endsWith('.stl')).map(([n,b])=>[n,hash(b)])),
    runtimeHashes:Object.fromEntries(await Promise.all(['assembly/playback.js','assembly/guide.js','viewer.js','model.js'].map(async n=>[n,hash(await readFile(new URL('../../../software/cadagent/webkit/'+n,import.meta.url)))]))),
    harnessSha256:hash(await readFile(new URL(import.meta.url))), cases:[], samples:[], maxToleranceMm:.002 };
  for (const consumer of ['guide','mini']) {
    const open = async variant => {
      await page.goto(consumer === 'guide' ? `${site.url}/kit/viewer.html?guide=/${variant}/guide.json` : `${site.url}/${variant}/index.html`);
      await page.waitForFunction(kind => kind === 'guide' ? document.body.dataset.ready === '1' : [...document.querySelectorAll('cad-model')].every(m => m.dataset.state === 'ready'), consumer);
      await page.evaluate(async ({ consumer, corners }) => {
        const THREE = await import('/kit/vendor/three/three.module.min.js');
        window.__serialTHREE = THREE; window.__serialConsumer = consumer;
        if (consumer === 'guide') {
          const v = window.__viewer; v.reset(); window.__serialPlayer = window.__guide.controller.createPlayback({durationMs:100});
          v.parts[0].mesh.parent.updateWorldMatrix(true,true); window.__serialBasis = v.parts[0].mesh.parent.matrixWorld.clone().invert();
          window.__serialIndices = Object.fromEntries(v.parts.map(p => [p.name,corners[p.name].map(point => {
            const a = p.mesh.geometry.attributes.position; for(let i=0;i<a.count;i++) if(point.every((n,k)=>Math.abs(a.array[3*i+k]-n)<.002)) return i;
            throw new Error('Native source landmark missing');
          })]));
        } else {
          const el = document.querySelector('cad-model'), {decodeModel,inflate} = await import('/kit/model.js');
          const model = await (await fetch(el.getAttribute('src'))).json(), bin = await (await fetch(new URL(model.bin,new URL(el.getAttribute('src'),location.href)))).arrayBuffer();
          const decoded = decodeModel(model,await inflate(bin));
          window.__serialIndices = Object.fromEntries(model.parts.map((p,i) => [p.name,corners[p.name].map(point => {
            const d=decoded[i]; for(let j=0;j<d.index.length;j++) if(point.every((n,k)=>Math.abs(d.positions[3*d.index[j]+k]-n)<.002)) return j;
            throw new Error('Packed native landmark missing');
          })]));
          const first = el.captureAssemblyLandmarks(window.__serialIndices);
          window.__serialBasis = new THREE.Matrix4().fromArray(first.cadToWorld).invert();
        }
        window.__serialCapture = () => {
          let components;
          if (consumer === 'guide') {
            const v=window.__viewer; v.stage.root.updateMatrixWorld(true); v.stage.renderer.render(v.stage.scene,v.stage.camera);
            components=Object.fromEntries(v.parts.map(p=>[p.name,window.__serialIndices[p.name].map(i=>new THREE.Vector3().fromBufferAttribute(p.mesh.geometry.attributes.position,i).applyMatrix4(p.mesh.matrixWorld).toArray())]));
          } else components=document.querySelector('cad-model').captureAssemblyLandmarks(window.__serialIndices).components;
          return Object.fromEntries(Object.entries(components).map(([name,points])=>[name,points.map(point=>new THREE.Vector3(...point).applyMatrix4(window.__serialBasis).toArray())]));
        };
      }, {consumer,corners:serialCorners});
    };
    const seek = async position => {
      const before = await page.evaluate(() => window.__serialConsumer === 'mini' ? document.querySelector('cad-model').frames : 0);
      await page.evaluate(position => {
        if(window.__serialConsumer === 'guide') window.__serialPlayer.seek(position);
        else document.querySelector('cad-model').setExplode(1-position/2);
      },position);
      if (consumer === 'mini') await page.waitForFunction(before => document.querySelector('cad-model').frames > before,before);
      return page.evaluate(()=>window.__serialCapture());
    };
    await open('serial');
    // Direct/nonmonotone seeks are the same absolute trajectory as reverse elapsed time.
    for (const [i,position] of [2,1.5,1,.5,.25,0,1.5,.25,2].entries()) {
      const actual=await seek(position);checkSerial(actual,position);
      if(i===1||i===4)packet.samples.push({consumer,position,components:actual});
    }
    if (consumer === 'guide') {
      const actual = await page.evaluate(() => {
        const p=window.__serialPlayer;p.seek(2);p.reverse();p.play();p.tick(.05);return window.__serialCapture();
      }); checkSerial(actual,1.5);
      const restored = await page.evaluate(() => {
        const v=window.__viewer,T=window.__serialTHREE,p=v.parts.find(p=>p.name==='plate'),parent=p.mesh.parent;
        const group=new T.Group();group.rotation.z=.7;group.position.set(12,3,2);parent.add(group);group.add(p.mesh);
        window.__serialPlayer.seek(.5);const actual=window.__serialCapture();parent.attach(p.mesh);group.removeFromParent();return actual;
      }); checkSerial(restored,.5);
      for (const fault of ['units','parent','fixed']) {
        const mutant=await page.evaluate(fault=>{
          window.__serialPlayer.seek(.5);const v=window.__viewer,m=v.parts.find(p=>p.name===(fault==='fixed'?'base':'plate')).mesh;
          if(fault==='units')m.scale.multiplyScalar(1000);else m.position.x+=7;
          m.updateMatrixWorld(true);return window.__serialCapture();
        },fault);assert.throws(()=>checkSerial(mutant,.5),`Actual ${fault} mutation must fail independent source landmarks`);
      }
      await page.evaluate(()=>window.__serialPlayer.reset());checkSerial(await page.evaluate(()=>window.__serialCapture()),2);
    } else {
      const second=await page.evaluate(()=>{const models=document.querySelectorAll('cad-model');return {frames:models[1].frames,first:models[0].stats.parts,second:models[1].stats.parts};});
      assert.equal(second.first,5);assert.equal(second.second,5);
    }
    packet.cases.push({consumer,case:'native-world-corners-seek-reverse-reset',samples:9,parkedVisible:true});
    for (const [variant,position] of [['serial-wrong-axis',.25],['serial-wrong-order',1.5]]) {
      await open(variant);const mutant=await seek(position);assert.throws(()=>checkSerial(mutant,position),`${consumer} ${variant} must fail independent physical oracle`);
      packet.cases.push({consumer,case:variant,rejectedByIndependentOracle:true});
    }
    await page.goto(consumer==='guide'?`${site.url}/kit/viewer.html?guide=/serial-stale/guide.json`:`${site.url}/serial-stale/index.html`);
    if(consumer==='guide'){await page.getByRole('button',{name:'Retry model',exact:true}).waitFor();assert.equal(await page.locator('#app canvas').count(),0);}
    else {await page.waitForFunction(()=>document.querySelector('cad-model').dataset.state==='error');assert.match(await page.locator('cad-model').first().getAttribute('data-error'),/SHA-256/);}
    packet.cases.push({consumer,case:'stale-plan-refused',radialFallback:false});
  }
  const phone=await browser.newContext({viewport:{width:320,height:700},deviceScaleFactor:2,reducedMotion:'reduce'});
  const phonePage=await phone.newPage();phonePage.on('pageerror',e=>errors.push(e.message));phonePage.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
  try {
    await phonePage.goto(`${site.url}/serial/index.html`);await phonePage.waitForFunction(()=>[...document.querySelectorAll('cad-model')].every(m=>m.dataset.state==='ready'));
    const button=phonePage.getByRole('button',{name:'Explode',exact:true}).first();await button.click();
    assert.equal(await button.getAttribute('aria-pressed'),'true');await button.focus();await phonePage.keyboard.press('Space');assert.equal(await button.getAttribute('aria-pressed'),'false');
    assert.equal(await phonePage.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
    await phonePage.screenshot({path:`${out}/${engine.name()}-serial-320.png`});
    packet.cases.push({case:'320px-dpr2-reduced-motion-keyboard-static',twoMiniViewers:true});
  } finally {await phone.close();}
  packet.errors=[...errors];packet.consoleErrors=[...consoleErrors];assert.deepEqual(packet.errors,[]);assert.deepEqual(packet.consoleErrors,[]);packet.passed=true;
  await writeFile(`${out}/${engine.name()}-serial-plan.json`,JSON.stringify(packet,null,2));
  cases.push(...packet.cases);
}
try {
  cors = await serveWebkit(new Map([['/part.stl', (_, res) => { res.setHeader('Access-Control-Allow-Origin', '*'); res.end(legacyShape.bytes); }]]));
  for (const [kind, file] of [['absolute', site.url + '/legacy/small%20part.stl'], ['root', '/legacy/small%20part.stl'], ['cors', cors.url + '/part.stl']]) routes.set(`/legacy/${kind}.json`, (_, res) => res.end(encode({ parts: [{ name: 'Published pan base fixture', file, color: 'steelblue', bounds_mm: legacyShape.bounds }] })));
routes.set('/legacy/redirect.stl', (_, res) => { res.writeHead(302, { Location: '/legacy/small%20part.stl' }); res.end(); });
routes.set('/legacy/redirect.json', (_, res) => res.end(encode({ parts: [{ name: 'redirect', file: '/legacy/redirect.stl', color: 'steelblue', bounds_mm: legacyShape.bounds }] })));
  browser = await engine.launch(engine === chromium ? { channel: process.env.PLAYWRIGHT_CHANNEL === 'chromium' ? undefined : 'chrome', headless: true } : { headless: true });
  const context = await browser.newContext({ viewport: { width: 1100, height: 800 } });
  const page = await context.newPage(); page.on('pageerror', error => errors.push(error.message)); page.on('console', message => {if(message.type()==='error')consoleErrors.push(message.text());});
  const visit = async (version, viewport = { width: 1100, height: 800 }) => {
    await page.setViewportSize(viewport);
    await page.goto(`${site.url}/kit/viewer.html?guide=${encodeURIComponent(`/${version}/guide.json`)}`);
    await page.waitForFunction(() => document.body.dataset.ready === '1', null, { timeout: 15000 });
  };
  const inspect = () => page.evaluate(async () => {
    const THREE = await import('/kit/vendor/three/three.module.min.js'), v = window.__viewer;
    v.stage.root.updateMatrixWorld(true);
    return v.parts.map(p => ({ name: p.name, visible: p.mesh.visible, offset: p.mesh.position.toArray(), world: p.mesh.getWorldPosition(new THREE.Vector3()).toArray(), opacity: p.mesh.material.opacity, transparent: p.mesh.material.transparent, depthWrite: p.mesh.material.depthWrite, wireframe: p.mesh.material.wireframe, emissive: p.mesh.material.emissive.getHex(), color: p.mesh.material.color.getHex(), uuid: p.mesh.uuid }));
  });
  await serialBrowserChecks(page, browser);
  if (!process.env.ASSEMBLY_PLAN_ONLY) {
  const v1UUIDs = [];
  for (const [index, version] of versions.entries()) {
    await visit(version);
    assert.match(await page.locator('.guide-version').innerText(), new RegExp(`${version}.*${String(index + 1).repeat(10)}`));
    const before = await inspect(); assert.deepEqual(before.map(p => p.visible), [true, false, false]);
    if (!index) v1UUIDs.push(...before.map(p => p.uuid)); else assert.ok(before.every(p => !v1UUIDs.includes(p.uuid)));
    await page.getByRole('button', { name: 'Next', exact: true }).click();
    const forward = await inspect(); assert.deepEqual(forward.map(p => p.visible), [true, true, true]);
    // Independent CAD [0.6,-1,-0.35] -> stage [0.6,-0.35,1], including the authored underside view.
    const expectedDirection = [0.6, -0.35, 1].map(n => n / Math.hypot(0.6, 0.35, 1));
    near(await page.evaluate(() => { const s = window.__viewer.stage; return s.camera.position.clone().sub(s.controls.target).normalize().toArray(); }), expectedDirection);
    assert.deepEqual(forward.map(p => p.opacity), [0.2, 1, 1]); assert.deepEqual(forward.map(p => p.depthWrite), [false, true, true]);
    // Independent physical expectations, not read back from the guide: CAD +Z is stage +Y and mm -> m once.
    near(forward[1].world.map((n, axis) => n - before[1].world[axis]), [0, 0.025 + index * 0.005, 0]);
    assert.ok(forward[1].emissive > 0 && forward[2].emissive > 0 && forward[0].emissive === 0);
    await page.getByRole('button', { name: 'Previous', exact: true }).click();
    await page.getByLabel('Instruction step', { exact: true }).selectOption('screws');
    const direct = await inspect(); assert.deepEqual(direct.map(p => p.offset), forward.map(p => p.offset));
    await page.getByLabel('Instruction display', { exact: true }).selectOption('wireframe'); assert.ok((await inspect()).every(p => p.wireframe));
    await page.getByLabel('Instruction display', { exact: true }).selectOption('solid'); assert.ok((await inspect()).every(p => !p.wireframe && p.opacity === 1));
    await page.evaluate(() => window.__viewer.setSelection('screw#1'));
    await page.getByLabel('Selected part appearance', { exact: true }).selectOption('transparent');
    assert.deepEqual((await inspect()).map(p => p.opacity), [1, 0.2, 1], 'Only the selected new screw becomes transparent');
    await page.getByLabel('Selected part appearance', { exact: true }).selectOption('wireframe');
    assert.deepEqual((await inspect()).map(p => p.wireframe), [false, true, false]);
    await page.getByLabel('Instruction step', { exact: true }).selectOption('base');
    await page.getByLabel('Instruction step', { exact: true }).selectOption('screws');
    assert.deepEqual(await page.evaluate(() => window.__viewer.getState().partModes), {});
    assert.ok((await inspect()).every(p => p.opacity === 1 && !p.wireframe));
    await page.evaluate(() => { const v = window.__viewer; v.setSelection('screw#2'); v.applyState({ ...v.getState(), isolate: ['screw#2'] }); });
    assert.deepEqual((await inspect()).map(p => p.visible), [false, false, true]);
    await page.getByRole('button', { name: 'Assembled', exact: true }).click();
    assert.equal(await page.getByLabel('Instruction display', { exact: true }).inputValue(), 'solid');
    assert.equal(await page.locator('.guide-explode').isChecked(), false);
    assert.equal(await page.getByLabel('Instruction step', { exact: true }).inputValue(), '');
    assert.equal(await page.getByLabel('Selected part appearance', { exact: true }).isDisabled(), true);
    assert.deepEqual(await page.evaluate(() => window.__viewer.getState().partModes), {});
    assert.match(await page.locator('.guide-text').innerText(), /Assembled view/);
    const reset = await inspect(); assert.ok(reset.every(p => p.visible && p.offset.every(n => n === 0) && p.opacity === 1 && !p.wireframe && p.emissive === 0));
    assert.deepEqual(reset.map(p => p.color), before.map(p => p.color));
    // Real picking: project the visible base centre and click its canvas position.
    const point = await page.evaluate(async () => { const THREE = await import('/kit/vendor/three/three.module.min.js'), v = window.__viewer, p = v.parts[0]; const q = new THREE.Vector3(...p.center.toArray()); p.mesh.localToWorld(q); q.project(v.stage.camera); const r = v.stage.renderer.domElement.getBoundingClientRect(); return [r.left + (q.x + 1) * r.width / 2, r.top + (1 - q.y) * r.height / 2]; });
    const clickTarget = await page.evaluate(([x, y]) => ({ x, y, element: document.elementFromPoint(x, y)?.tagName }), point);
    cases.push({ pickingTarget: clickTarget });
    assert.equal(clickTarget.element, 'CANVAS', 'Projected part must be reachable through the real canvas');
    await page.mouse.click(...point); assert.ok(await page.evaluate(() => window.__viewer.getState().selected !== null));
    await page.screenshot({ path: `${out}/${engine.name()}-${version}.png` });
    cases.push({ version, snapshot: await page.evaluate(() => window.__guide.guide.snapshot), coordinateDelta: forward[1].world.map((n, axis) => n - before[1].world[axis]), reset: true });
    const playback = await page.evaluate(async () => {
      const { createGuidePlayback } = await import('/kit/assembly/guide.js');
      const player = createGuidePlayback(window.__guide.controller, { durationMs: 400,
        installOrderByStep: { base: ['base'], screws: ['screw#2', 'screw#1'] }, referenceStepIDs: [] });
      window.__player = player; player.play(); for (let i = 0; i < 4; i++) player.tick(0.1);
      player.tick(0.1); return player.getState();
    });
    assert.equal(playback.partId, 'screw#2'); assert.equal(playback.progress, 0.25);
    const moving = await inspect(); assert.deepEqual(moving.map(p => p.visible), [true, false, true]);
    assert.deepEqual(moving.map(p => p.opacity), [1, 1, 1]);
    // Independently authored fixture distances: 25/30/35 mm, at 25% installation -> 18.75/22.5/26.25 mm.
    near(moving[2].world.map((n, axis) => n - before[2].world[axis]), [0, (18.75 + index * 3.75) / 1000, 0]);
    const paused = await page.evaluate(() => { window.__player.pause(); return window.__viewer.parts[2].mesh.position.toArray(); });
    await page.evaluate(() => window.__player.tick(100)); assert.deepEqual((await inspect())[2].offset, paused);
    await page.evaluate(() => { window.__player.play(); for (let i = 0; i < 7; i++) window.__player.tick(0.1); });
    assert.equal(await page.evaluate(() => window.__player.getState().status), 'ended');
    const installed = await inspect(); assert.ok(installed.every(p => p.visible && p.offset.every(n => n === 0)));
    await page.evaluate(() => { window.__guide.controller.applyStep('base'); window.__player.play(); window.__guide.controller.applyStep('screws'); });
    assert.equal(await page.evaluate(() => window.__player.getState().status), 'paused');
    await page.evaluate(() => window.__player.dispose()); cases.push({ version, orderedPlaybackWorldPoses: true });
  }
  await visit('framing');
  const hiddenFrame = await page.evaluate(async () => {
    const { createGuidePlayback } = await import('/kit/assembly/guide.js'), THREE = await import('/kit/vendor/three/three.module.min.js');
    const v = window.__viewer, player = createGuidePlayback(window.__guide.controller, { durationMs: 100,
      installOrderByStep: { base: ['base'], screws: ['screw#2', 'screw#1'] } });
    player.play(); player.tick(0.1);
    const points = () => {
      const p = v.parts[1], b = new THREE.Box3().setFromObject(p.mesh);
      return Array.from({ length: 8 }, (_, i) => new THREE.Vector3(i & 1 ? b.max.x : b.min.x, i & 2 ? b.max.y : b.min.y, i & 4 ? b.max.z : b.min.z).project(v.stage.camera)).map(q => [q.x, q.y]);
    };
    v.frameParts(['base', 'screw#2'], [0.001, -0.001, 1]); const excludesFuture = points().some(([x, y]) => Math.abs(x) > 1 || Math.abs(y) > 1);
    v.frameParts(['base', 'screw#1', 'screw#2'], [0.001, -0.001, 1], { includeHidden: true });
    const included = points().every(([x, y]) => Math.abs(x) <= 1 && Math.abs(y) <= 1);
    const result = { excludesFuture, included, hidden: !v.parts[1].mesh.visible, offset: v.parts[1].mesh.position.toArray() };
    player.dispose(); return result;
  });
  assert.deepEqual(hiddenFrame, { excludesFuture: true, included: true, hidden: true, offset: [120, 0, 25] }); cases.push({ hiddenFutureFraming: hiddenFrame });
  // Fault controls prove the independent coordinate check detects 1000x units, wrong frame and doubled offsets.
  await visit('v1');
  const underside = await page.evaluate(() => {
    const v = window.__viewer, s = v.stage;
    const direction = () => s.camera.position.clone().sub(s.controls.target).normalize().toArray();
    const expected = [0.6, -0.35, 1].map(n => n / Math.hypot(0.6, 0.35, 1));
    const matches = () => direction().every((n, i) => Math.abs(n - expected[i]) < 1e-6);
    const normalLimit = s.controls.maxPolarAngle;
    s.controls.maxPolarAngle = 1.5; window.__guide.controller.applyStep('screws');
    const oldClampRejected = !matches();
    s.controls.maxPolarAngle = normalLimit; window.__guide.controller.applyStep('screws');
    return { oldClampRejected, restored: matches(), direction: direction(), normalLimit };
  });
  assert.equal(underside.oldClampRejected, true); assert.equal(underside.restored, true);
  assert.equal(underside.normalLimit, Math.PI); cases.push({ undersideCamera: underside });
  const rejects = await page.evaluate(() => {
    const v = window.__viewer, guide = window.__guide.controller;
    const check = () => { const p = v.parts[1].mesh.position; return Math.abs(p.x) < 1e-9 && Math.abs(p.y) < 1e-9 && Math.abs(p.z - 25) < 1e-9; };
    const results = [];
    for (const offset of [[0, 0, 25000], [0, 25, 0], [0, 0, 50]]) { guide.applyStep('screws'); v.parts[1].mesh.position.fromArray(offset); results.push(!check()); }
    guide.applyStep('screws'); results.push(check()); return results;
  }); assert.deepEqual(rejects, [true, true, true, true]); cases.push({ wrongUnitFrameDoubleOffsetControls: rejects });
  // Actual raster clipping on independent CAD face landmarks, not just a mirrored plane-property assertion.
  const sections = await page.evaluate(() => {
    const v = window.__viewer, s = v.stage; v.reset(); s.stop();
    // Keep the real physical material and clipping shader, but give this visibility fixture an emissive signal.
    // Removing another half must not change a retained landmark's shadow and masquerade as missing geometry.
    for (const [i, part] of v.parts.entries()) {
      const material = part.mesh.material;
      material.color.setHex(0); material.emissive.setHex(i ? 0xffaa00 : 0xff00ff);
      material.emissiveIntensity = 1; material.specularIntensity = 0; material.clearcoat = 0;
    }
    const names = ['base', 'screw#1', 'screw#2'], gl = s.renderer.getContext(), canvas = s.renderer.domElement;
    const rgb = point => {
      const q = v.parts[0].mesh.position.clone().fromArray(point); v.parts[0].mesh.localToWorld(q); q.project(s.camera);
      const bytes = new Uint8Array(4);
      gl.readPixels(Math.floor((q.x + 1) * canvas.width / 2), Math.floor((q.y + 1) * canvas.height / 2), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, bytes);
      return [...bytes].slice(0, 3);
    };
    const sample = points => { s.renderer.render(s.scene, s.camera); return points.map(rgb); };
    const distance = (a, b) => Math.max(...a.map((n, i) => Math.abs(n - b[i])));
    const rows = [];
    for (const [axis, direction, points, wrongAxis] of [
      ['x', [0.001, -0.001, 1], [[10.5, 10.5, 28], [30.5, 10.5, 28]], 'y'],
      ['y', [0.001, -0.001, 1], [[20, 20, 8], [20, 25, 8]], 'z'],
      ['z', [0.001, -1, 0.001], [[10.5, 8, 18], [10.5, 8, 24]], 'x'],
    ]) {
      v.setSectionPlane({ axis, flipped: false }); v.setSection(1); v.frameParts(names, direction);
      const baseline = sample(points);
      v.setSection(0.25); const ordinary = sample(points), originalConstant = v.parts[0].mesh.material.clippingPlanes[0].constant;
      v.setSectionPlane({ axis, flipped: true }); const flipped = sample(points);
      v.parts[0].mesh.material.clippingPlanes[0].constant = originalConstant;
      const wrongFlip = sample(points); // deliberate normal-only flip: location changes instead of retained side alone
      v.setSectionPlane({ axis: wrongAxis, flipped: false }); const wrong = sample(points);
      const pattern = colors => colors.map((color, i) => distance(color, baseline[i]) < 20);
      rows.push({ axis, baseline, ordinary, flipped, wrongFlip, wrong, ordinaryPattern: pattern(ordinary), flippedPattern: pattern(flipped), wrongFlipPattern: pattern(wrongFlip), wrongPattern: pattern(wrong) });
    }
    v.setSectionPlane({ axis: 'y', flipped: true }); v.setSection(1);
    const disabled = { ...v.getSectionState(), constant: v.parts[0].mesh.material.clippingPlanes[0].constant };
    const disabledPattern = sample([[10.5, 8, 18], [10.5, 8, 24]]).map((color, i) => distance(color, rows[2].baseline[i]) < 20);
    const copy = v.getSectionState(); copy.axis = 'z';
    const before = JSON.stringify(v.getSectionState()), invalid = [];
    for (const option of [{ axis: 'oblique' }, { axis: 'constructor' }, { axis: 'x', flipped: 1 }]) {
      try { v.setSectionPlane(option); invalid.push(false); } catch { invalid.push(JSON.stringify(v.getSectionState()) === before); }
    }
    v.reset(); const reset = v.getSectionState(); s.start();
    return { rows, disabled, disabledPattern, invalid, reset };
  });
  await writeFile(`${out}/${engine.name()}-section-pixels.json`, JSON.stringify(sections, null, 2));
  for (const row of sections.rows) {
    assert.deepEqual(row.ordinaryPattern, [true, false], JSON.stringify(row));
    assert.deepEqual(row.flippedPattern, [false, true], JSON.stringify(row));
    assert.notDeepEqual(row.wrongFlipPattern, [false, true], 'Normal-only flip must fail the actual off-centre pixel control');
    assert.notDeepEqual(row.wrongPattern, [true, false], 'Wrong CAD axis must fail the actual pixel control');
  }
  assert.deepEqual(sections.disabled, { axis: 'y', flipped: true, depth: 1, constant: 1e9 });
  assert.deepEqual(sections.disabledPattern, [true, true]);
  assert.deepEqual(sections.invalid, [true, true, true]); assert.deepEqual(sections.reset, { axis: 'x', flipped: false, depth: 1 });
  cases.push({ actualOrthogonalClipping: sections });
  // Mount the same shared viewer with optional callbacks, then drive real pointer events over a hard-coded CAD face.
  await page.evaluate(async () => {
    const { createViewer } = await import('/kit/viewer.js'); window.__viewer.dispose(); window.__hoverEvents = []; window.__selectEvents = [];
    window.__viewer = await createViewer({ app: document.querySelector('#app'), panel: document.querySelector('#panel'),
      manifestUrl: new URL('/v1/view.json', location.href).href, manifest: window.__guide.manifest, guideBound: true,
      onHover: (name, point) => window.__hoverEvents.push({ name, point }),
      onSelect: (name, interaction) => window.__selectEvents.push({ name, interaction }) });
    window.__viewer.stage.controls.enableDamping = false;
    window.__viewer.frameParts(['base', 'screw#1', 'screw#2'], [0.001, -0.001, 1]);
  });
  const hoverPoint = await page.evaluate(() => {
    const v = window.__viewer, q = v.parts[0].mesh.position.clone().set(10.5, 10.5, 28); v.parts[0].mesh.localToWorld(q); q.project(v.stage.camera);
    const r = v.stage.renderer.domElement.getBoundingClientRect(); return [r.left + (q.x + 1) * r.width / 2, r.top + (1 - q.y) * r.height / 2];
  });
  await page.mouse.move(...hoverPoint); await page.waitForFunction(() => window.__hoverEvents.at(-1)?.name === 'screw#1');
  await page.mouse.wheel(0, 30); await page.waitForFunction(() => window.__hoverEvents.at(-1)?.name === null);
  await page.evaluate(() => window.__viewer.frameParts(['base', 'screw#1', 'screw#2'], [0.001, -0.001, 1]));
  await page.mouse.move(hoverPoint[0] + 1, hoverPoint[1]); await page.waitForFunction(() => window.__hoverEvents.at(-1)?.name === 'screw#1');
  await page.mouse.click(...hoverPoint); await page.mouse.click(...hoverPoint);
  const pointerSelections = await page.evaluate(() => window.__selectEvents);
  assert.deepEqual(pointerSelections.map(row => row.name), ['screw#1', 'screw#1']);
  assert.ok(pointerSelections.every(row => row.interaction.pointerType === 'mouse' && Number.isFinite(row.interaction.clientX)));
  await page.evaluate(() => window.__viewer.setSelection('screw#1')); assert.equal(await page.evaluate(() => window.__selectEvents.length), 2);
  const clippedPoint = await page.evaluate(() => {
    const v = window.__viewer; v.setSection(0.25);
    const q = v.parts[0].mesh.position.clone().set(30.5, 10.5, 28); v.parts[0].mesh.localToWorld(q); q.project(v.stage.camera);
    const r = v.stage.renderer.domElement.getBoundingClientRect(); return [r.left + (q.x + 1) * r.width / 2, r.top + (1 - q.y) * r.height / 2];
  });
  await page.mouse.move(...clippedPoint); await page.mouse.click(...clippedPoint);
  assert.equal(await page.evaluate(() => window.__selectEvents.at(-1).name), null, 'A ray hit discarded by the actual section cannot select an invisible surface');
  await page.evaluate(() => { window.__viewer.setSection(1); window.__viewer.setSelection('screw#1'); });
  const selectionsBeforeDrag = await page.evaluate(() => window.__selectEvents.length);
  await page.mouse.move(...hoverPoint); await page.mouse.down(); await page.mouse.move(hoverPoint[0] + 60, hoverPoint[1] + 10, { steps: 4 }); await page.mouse.up();
  assert.equal(await page.evaluate(() => window.__selectEvents.length), selectionsBeforeDrag, 'Orbit drag cannot select or intercept input');
  await page.evaluate(() => { const v = window.__viewer; v.frameParts(['base', 'screw#1', 'screw#2'], [0.001, -0.001, 1]); v.parts[1].mesh.parent.visible = false; });
  await page.mouse.move(hoverPoint[0] + 1, hoverPoint[1]); await page.mouse.click(...hoverPoint);
  assert.equal(await page.evaluate(() => window.__selectEvents.at(-1).name), null, 'Hidden ancestor is not raycast-pickable');
  await page.evaluate(() => { window.__viewer.parts[1].mesh.parent.visible = true; });
  await page.mouse.move(hoverPoint[0] + 2, hoverPoint[1]); await page.waitForFunction(() => window.__hoverEvents.at(-1)?.name === 'screw#1');
  await page.mouse.move(0, 0); await page.waitForFunction(() => window.__hoverEvents.at(-1)?.name === null);
  const disposedCallbacks = await page.evaluate(async () => {
    const v = window.__viewer, canvas = v.stage.renderer.domElement; v.dispose();
    const before = [window.__hoverEvents.length, window.__selectEvents.length];
    canvas.dispatchEvent(new PointerEvent('pointermove', { clientX: 50, clientY: 50, pointerType: 'mouse' }));
    canvas.dispatchEvent(new PointerEvent('pointerdown', { clientX: 50, clientY: 50, pointerId: 1 }));
    canvas.dispatchEvent(new PointerEvent('pointerup', { clientX: 50, clientY: 50, pointerId: 1 }));
    await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame);
    return { before, after: [window.__hoverEvents.length, window.__selectEvents.length] };
  });
  assert.deepEqual(disposedCallbacks.before, disposedCallbacks.after); cases.push({ actualHoverSelectionDragHiddenDispose: true });
  const touchContext = await browser.newContext({ viewport: { width: 1100, height: 800 }, hasTouch: true });
  const touchPage = await touchContext.newPage(); touchPage.on('pageerror', error => errors.push(error.message));
  await touchPage.goto(`${site.url}/kit/viewer.html?guide=/v1/guide.json`);
  await touchPage.waitForFunction(() => document.body?.dataset.ready === '1', null, { timeout: 15000 });
  const touchPoint = await touchPage.evaluate(async () => {
    const loaded = window.__guide; loaded.dispose();
    const { createViewer } = await import('/kit/viewer.js'); window.__touchSelections = []; window.__touchHovers = [];
    const v = window.__viewer = await createViewer({ app: document.querySelector('#app'), panel: document.querySelector('#panel'),
      manifestUrl: loaded.manifestUrl, manifest: loaded.manifest, guideBound: true,
      onSelect: (name, interaction) => window.__touchSelections.push({ name, interaction }), onHover: name => window.__touchHovers.push(name) });
    v.frameParts(['base', 'screw#1', 'screw#2'], [0.001, -0.001, 1]);
    const q = v.parts[0].mesh.position.clone().set(10.5, 10.5, 28); v.parts[0].mesh.localToWorld(q); q.project(v.stage.camera);
    const r = v.stage.renderer.domElement.getBoundingClientRect(); return [r.left + (q.x + 1) * r.width / 2, r.top + (1 - q.y) * r.height / 2];
  });
  await touchPage.touchscreen.tap(...touchPoint);
  assert.deepEqual(await touchPage.evaluate(() => window.__touchSelections.map(row => [row.name, row.interaction.pointerType])), [['screw#1', 'touch']]);
  assert.deepEqual(await touchPage.evaluate(() => window.__touchHovers), [], 'Touch selects without a synthetic hover tooltip');
  await touchPage.evaluate(() => window.__viewer.dispose()); await touchContext.close(); cases.push({ nativeTouchSelection: true });
  // Legacy manifest path and API remain usable.
  await page.goto(`${site.url}/kit/viewer.html?manifest=/v1/view.json&explode=0.5&section=0.5`);
  await page.waitForFunction(() => document.body.dataset.ready === '1');
  assert.equal(await page.locator('#panel input[type=range]').nth(0).inputValue(), '0.5');
  assert.equal(await page.locator('#panel input[type=range]').nth(1).inputValue(), '0.5');
  assert.ok(await page.evaluate(() => window.__viewer.stage.renderer.info.render.calls > 0), 'Ready includes an actual drawn frame');
  assert.equal(await page.evaluate(() => window.__viewer.stage.controls.maxPolarAngle), 1.5, 'Ordinary viewer keeps its existing orbit limit');
  const unsubscribe = await page.evaluate(async () => {
    let count = 0; const cb = () => count++, stage = window.__viewer.stage;
    const first = stage.onFrame(cb), second = stage.onFrame(cb);
    first(); first(); await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame);
    const stillOwned = count > 0; second(); const before = count;
    await new Promise(requestAnimationFrame); await new Promise(requestAnimationFrame);
    return { stillOwned, stopped: count === before };
  });
  assert.deepEqual(unsubscribe, { stillOwned: true, stopped: true }); cases.push({ frameUnsubscribe: unsubscribe });
  assert.ok((await inspect()).some(p => p.offset.some(n => n !== 0))); await page.evaluate(() => window.__viewer.reset());
  assert.ok((await inspect()).every(p => p.offset.every(n => n === 0)));
  await page.evaluate(() => { const color = document.querySelector('#panel input[type=color]'); color.value = '#aa0011'; color.dispatchEvent(new Event('input')); window.__viewer.setExplode(0.2); });
  assert.equal((await inspect())[0].color, 0xaa0011, 'Legacy colour choice survives explode');
  await page.evaluate(() => window.__viewer.reset()); assert.equal((await inspect())[0].color, 0x487ca8);
  cases.push({ legacy: true });
  await page.goto(`${site.url}/kit/viewer.html?manifest=/legacy/view.json`); await page.waitForFunction(() => document.body.dataset.ready === '1');
  assert.equal((await inspect())[0].color, 0x4682b4); cases.push({ legacySpacesAndCSSColor: true });
  for (const kind of ['absolute', 'root', 'cors', 'redirect']) {
    await page.goto(`${site.url}/kit/viewer.html?manifest=/legacy/${kind}.json`); await page.waitForFunction(() => document.body.dataset.ready === '1');
    assert.equal((await inspect())[0].color, 0x4682b4); cases.push({ legacyURL: kind });
  }
  await visit('proto');
  assert.ok((await inspect()).every(p => p.offset.every(Number.isFinite)), 'prototype-shaped part names retain a zero finite baseline');
  const prototypePlayback = await page.evaluate(async () => {
    const { createGuidePlayback } = await import('/kit/assembly/guide.js');
    const player = createGuidePlayback(window.__guide.controller, { durationMs: 100,
      installOrderByStep: { base: ['constructor'], screws: ['screw#2', 'screw#1'] } });
    player.play(); player.tick(0.1); player.tick(0.05);
    const result = { foundation: window.__viewer.parts[0].mesh.position.toArray(), moving: window.__viewer.parts[2].mesh.position.toArray() };
    player.dispose(); return result;
  });
  assert.deepEqual(prototypePlayback, { foundation: [0, 0, 0], moving: [0, 0, 20] });
  cases.push({ prototypePartName: true, prototypePlayback });
  // Corrupted mesh or cancelled/late load never mounts a partial scene.
  await page.route('**/v1/1.stl', route => route.fulfill({ body: Buffer.from('wrong bytes') }));
  await page.goto(`${site.url}/kit/viewer.html?guide=/v1/guide.json`); await page.getByRole('button', { name: 'Retry model', exact: true }).waitFor();
  assert.equal(await page.locator('#app canvas').count(), 0); assert.match(await page.locator('#panel').innerText(), /SHA-256/);
  await page.unroute('**/v1/1.stl'); await page.getByRole('button', { name: 'Retry model', exact: true }).click(); await page.waitForFunction(() => document.body.dataset.ready === '1');
  // Abort a held mesh, then release its late response: the retained scene cannot be replaced.
  const retained = await page.evaluate(() => window.__viewer.parts[0].mesh.uuid);
  let releaseLate, began;
  const downloading = new Promise(resolve => { began = resolve; });
  await page.route('**/late/0.stl', route => { began(); return new Promise(resolve => { releaseLate = async () => { try { await route.fulfill({ body: cube([0, 0, 0], [40, 30, 8]).bytes }); } catch {} resolve(); }; }); });
  await page.evaluate(async () => {
    const { createViewer } = await import('/kit/viewer.js');
    window.__pendingApp = document.createElement('div'); window.__pendingPanel = document.createElement('div');
    document.body.append(window.__pendingApp, window.__pendingPanel); window.__pendingAbort = new AbortController();
    window.__pendingResult = 'loading';
    createViewer({ app: window.__pendingApp, panel: window.__pendingPanel, manifestUrl: '/late/view.json', manifest: { ...window.__guide.manifest, parts: window.__guide.manifest.parts.map(p => ({ ...p, file: new URL('/late/' + p.file, location.href).href })) }, signal: window.__pendingAbort.signal, timeoutMs: 5000 })
      .then(v => { v.dispose(); window.__pendingResult = 'unexpected success'; }, () => { window.__pendingResult = 'aborted'; });
  });
  await downloading; await page.evaluate(() => window.__pendingAbort.abort());
  await page.waitForFunction(() => window.__pendingResult === 'aborted'); await releaseLate();
  assert.equal(await page.evaluate(() => window.__viewer.parts[0].mesh.uuid), retained);
  assert.equal(await page.evaluate(() => window.__pendingApp.querySelectorAll('canvas').length), 0);
  await page.evaluate(() => { window.__pendingApp.remove(); window.__pendingPanel.remove(); });
  await page.unroute('**/late/0.stl'); cases.push({ abortedLateLoadRetainsScene: true });
  const teardown = await page.evaluate(async () => {
    const v = window.__viewer; let geometries = 0, materials = 0;
    const sentinel = document.createElement('p'); sentinel.textContent = 'Caller-owned controls'; document.querySelector('#panel').append(sentinel);
    for (const p of v.parts) { p.mesh.geometry.addEventListener('dispose', () => geometries++); p.mesh.material.addEventListener('dispose', () => materials++); }
    v.dispose(); v.dispose(); let rejected = false; try { v.reset(); } catch { rejected = true; }
    const { createViewer } = await import('/kit/viewer.js'); const controller = new AbortController(); controller.abort();
    let cancelled = false; try { await createViewer({ app: document.querySelector('#app'), panel: document.querySelector('#panel'), manifestUrl: '/v1/view.json', signal: controller.signal }); } catch { cancelled = true; }
    return { geometries, materials, canvases: document.querySelectorAll('#app canvas').length, rejected, cancelled, callerControlsPreserved: sentinel.isConnected };
  }); assert.deepEqual(teardown, { geometries: 3, materials: 3, canvases: 0, rejected: true, cancelled: true, callerControlsPreserved: true }); cases.push({ teardown });
  for (const viewport of [{ width: 390, height: 844 }, { width: 844, height: 390 }]) {
    await visit('v1', viewport); await page.getByRole('button', { name: 'Next', exact: true }).focus(); await page.keyboard.press('Enter');
    assert.equal(await page.getByLabel('Instruction step', { exact: true }).inputValue(), 'screws');
    assert.ok(await page.locator('#app canvas').isVisible());
    const framed = await page.evaluate(async () => {
      const THREE = await import('/kit/vendor/three/three.module.min.js'), v = window.__viewer;
      v.stage.root.updateMatrixWorld(true); const r = v.stage.renderer.domElement.getBoundingClientRect(), header = document.querySelector('#topbar').getBoundingClientRect();
      const points = v.parts.filter(p => p.mesh.visible).flatMap(p => { const b = new THREE.Box3().setFromObject(p.mesh); return Array.from({ length: 8 }, (_, i) => new THREE.Vector3(i & 1 ? b.max.x : b.min.x, i & 2 ? b.max.y : b.min.y, i & 4 ? b.max.z : b.min.z).project(v.stage.camera)).map(q => [r.left + (q.x + 1) * r.width / 2, r.top + (1 - q.y) * r.height / 2]); });
      const panel = document.querySelector('#panel').getBoundingClientRect();
      return { points, top: Math.max(r.top, header.bottom), bottom: Math.min(r.bottom, panel.top > r.top + r.height / 2 ? panel.top : r.bottom), right: panel.left > r.left + r.width / 2 ? panel.left : r.right, left: r.left };
    });
    assert.ok(framed.points.every(([x, y]) => x >= framed.left - 1 && x <= framed.right + 1 && y >= framed.top - 1 && y <= framed.bottom + 1), JSON.stringify(framed));
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1); assert.equal(overflow, false);
    await page.screenshot({ path: `${out}/${engine.name()}-${viewport.width}.png` }); cases.push({ viewport, keyboard: true });
  }
  }
  assert.deepEqual(errors, []);
  await writeFile(`${out}/${engine.name()}-report.json`, JSON.stringify({ passed: true, cases, errors }, null, 2));
  console.log(JSON.stringify({ passed: true, engine: engine.name(), cases: cases.length, out }));
} catch (error) {
  for (const context of browser?.contexts() || []) for (const page of context.pages()) { try { await page.screenshot({ path: `${out}/${engine.name()}-failure.png` }); } catch {} }
  await writeFile(`${out}/${engine.name()}-failure.json`, JSON.stringify({ message: error.message, cases, errors }, null, 2)); throw error;
} finally { try { await browser?.close(); } finally { try { await site.close(); } finally { await cors?.close(); } } }
