import {toolkitExampleChecks} from './toolkit-examples-browser.mjs';
/** Toolkit uses the same site frame, local assets and browser/error recorder as Explore. */
export async function toolkitBrowserChecks({open,fail}) {
  await toolkitExampleChecks({open,fail});
  await scadaNativeNavigationChecks({open,fail});
  for(const width of [320,1366]) for(const color of ['light','dark']) {
    const {page,done}=await open('/toolkit/scada/elements?q=pump&category=rotating&kind=equipment',{width,color});
    try {
      await page.locator('[data-scada-filters]:visible').waitFor();
      const nav=page.getByRole('navigation',{name:'Main'}).getByRole('link',{name:'Toolkit',exact:true});
      if(await nav.getAttribute('href')!=='/toolkit'||await nav.getAttribute('aria-current')!=='page')fail('Toolkit navigation','missing canonical capability tab');
      if(await page.getByRole('searchbox').inputValue()!=='pump')fail('Toolkit filters','URL query was not restored');
      const visible=page.locator('[data-scada-card]:visible');
      const ids=await visible.evaluateAll(xs=>xs.map(x=>x.id));
      if(!ids.includes('equipment--pump')||ids.some(id=>!id.startsWith('equipment--')||!id.includes('pump')))fail('Toolkit filters',JSON.stringify(ids));
      if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))fail('Toolkit layout',`${width}px ${color} overflows`);
      const pump=page.locator('#equipment--pump'), image=pump.locator('img');
      await image.scrollIntoViewIfNeeded();
      await page.waitForFunction(()=>{const img=document.querySelector('#equipment--pump img');return img.complete&&img.naturalWidth>0;});
      const button=pump.getByRole('button',{name:'Try states'});await button.click();
      const art=page.locator('[data-scada-preview-art] [data-scada-type="pump"]');await art.waitFor();
      const contrast=await art.evaluate(element=>{
        const luminance=color=>{
          const channels=color.match(/[\d.]+/g).slice(0,3).map(Number).map(n=>{const c=n/255;return c<=.04045?c/12.92:((c+.055)/1.055)**2.4;});
          return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722;
        };
        const labels=[...element.querySelectorAll('.scada-component-gauges span,.scada-component-gauges strong')];
        if(!labels.length)return 0;
        const background=luminance(getComputedStyle(element.closest('[data-scada-preview-art]')).backgroundColor);
        return Math.min(...labels.map(label=>{
          const foreground=luminance(getComputedStyle(label).color);
          return (Math.max(foreground,background)+.05)/(Math.min(foreground,background)+.05);
        }));
      });
      if(contrast<4.5)fail('Toolkit preview readability',`${color} gauge-label contrast ${contrast.toFixed(2)}:1`);
      const smallestLabel=await art.locator('.scada-component-gauges small,.scada-component-gauges strong').evaluateAll(labels=>Math.min(...labels.map(label=>parseFloat(getComputedStyle(label).fontSize))));
      if(smallestLabel<12)fail('Toolkit preview readability',`dedicated preview gauge labels are ${smallestLabel}px`);
      const running=page.locator('[data-scada-state-fields] [name="running"]');await running.uncheck();
      if(await art.getAttribute('data-running')!=='false')fail('Toolkit preview','state field did not reach the actual renderer');
      const load=page.locator('[data-scada-state-fields] [name="load"]');
      if(await load.count()) {await load.fill('25');await load.press('Enter');if(!await page.locator('.toolkit-preview').isVisible())fail('Toolkit preview','Enter submitted the state form as navigation');await load.fill('');await running.check();if((await art.getAttribute('style')).includes('NaN'))fail('Toolkit preview','empty numeric input poisoned the renderer');}
      await page.keyboard.press('Escape');
      if(!await button.evaluate(el=>el===document.activeElement))fail('Toolkit preview','closing the modal lost keyboard focus');
      await page.getByRole('searchbox').fill('no-matching-equipment-123');
      if(await visible.count()||!await page.locator('[data-scada-empty]').isVisible())fail('Toolkit empty state','no-match state was not announced');
      await page.getByRole('button',{name:'Clear filters'}).click();
      if(new URL(page.url()).search)fail('Toolkit reset','filters were not removed from the URL');
    } finally {await done();}
  }
  for(const js of [true,false]) {
    const {page,done}=await open('/toolkit/scada/simulations',{js,width:390});
    try {
      const first=page.locator('[data-scada-card]').first();
      if(!(await first.getByRole('link',{name:'Run simulation'}).getAttribute('href')).endsWith('?scenario=wastewater-digester'))fail('Toolkit simulations','wastewater is not the featured target-owned launch');
      if(js) {
        await page.getByRole('searchbox').fill('winery');
        const cards=page.locator('[data-scada-card]:visible');
        if(await cards.count()!==1||!(await cards.first().textContent()).includes('Winery'))fail('Toolkit simulations','scenario search does not select the real inventory');
      } else if(await page.locator('[data-scada-card]').count()<60||await page.locator('[data-scada-filters]').isVisible())fail('Toolkit fallback','native simulation cards/controls are not usable without script');
    } finally {await done();}
  }
  const {page,done}=await open('/toolkit/scada/elements',{js:false,width:390});
  try {
    if(await page.locator('[data-scada-card]').count()<239||await page.locator('[data-scada-preview]:visible').count())fail('Toolkit native assets','gallery fallback lost the symbols or exposes inert buttons');
  } finally {await done();}
  const retry=await open('/toolkit/scada/elements?q=pump&kind=equipment');
  try {
    await retry.page.route('**/toolkit/scada/catalog.json',route=>route.fulfill({contentType:'application/json',body:'{"schema":"unsupported","elements":[]}'}));
    const pump=retry.page.locator('#equipment--pump'),button=pump.getByRole('button',{name:'Try states'});
    await button.click();await retry.page.locator('[data-scada-preview-error]').filter({hasText:'could not load'}).waitFor();
    await retry.page.keyboard.press('Escape');
    if(!await pump.getByRole('link',{name:'SVG asset'}).isVisible())fail('Toolkit preview failure','native asset link disappeared');
    await retry.page.unroute('**/toolkit/scada/catalog.json');
    await button.click();await retry.page.locator('[data-scada-preview-art] [data-scada-type="pump"]').waitFor();
    await retry.page.keyboard.press('Escape');
  } finally {await retry.done();}
}

/** Human documentation shares the existing frame; raw assets remain direct downloads. */
export async function scadaNativeNavigationChecks({open,fail}) {
  for(const options of [{width:320,color:'light',js:true},{width:1366,color:'dark',js:false}]) {
    for(const route of ['/toolkit/scada','/toolkit/scada/elements','/toolkit/scada/simulations']) {
      const {page,done}=await open(route,options);
      try {
        const nav=page.getByRole('navigation',{name:'Main'});
        if(await nav.getByRole('link',{name:'Toolkit',exact:true}).getAttribute('aria-current')!=='page')fail('SCADA native frame',`${route}: Toolkit is not the current main section`);
        // The shared compact header intentionally hides secondary links; the overview's agent section stays usable.
        const agents=nav.locator('a').filter({hasText:'For agents'});
        if(await agents.getAttribute('href')!=='/docs/agent-workflow'||options.width>=650&&!await agents.isVisible())fail('SCADA native frame',`${route}: shared agent entrypoint missing`);
        if(!/MIT-licensed/.test(await page.locator('.toolkit-license').textContent()))fail('SCADA terms',`${route}: project-owned terms are stale`);
        if(await page.locator('.toolkit-shell a[href^="/kit/scada/"][href$=".md"]').count())fail('SCADA native guides',`${route}: human documentation exits to raw Markdown`);
        if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1))fail('SCADA native frame',`${route} @${options.width}: horizontal overflow`);
        if(route!=='/toolkit/scada')continue;
        for(const label of ['Use & extend','UI library','Models & equations','Local setup & packaging','Replace equations','For agents']) {
          const link=page.locator('.toolkit-shell').getByRole('link',{name:label,exact:true});
          const destination=new URL(await link.getAttribute('href'),page.url());
          await link.scrollIntoViewIfNeeded();await link.focus();
          if(options.js)await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
          else await link.screenshot(); // Paint the focused native link without scheduling disabled page script.
          await Promise.all([page.waitForURL(url=>url.origin===destination.origin&&url.pathname===destination.pathname,{waitUntil:'domcontentloaded'}),link.press('Enter')]);
          await page.getByRole('navigation',{name:'Main'}).waitFor();
          if(!await page.getByRole('navigation',{name:'Main'}).getByRole('link',{name:'Toolkit',exact:true}).isVisible())fail('SCADA native guides',`${label}: shared navigation disappeared`);
          if(!await page.locator('.site-footer').getByRole('link',{name:'Valpatel Software LLC',exact:true}).count())fail('SCADA native guides',`${label}: shared attribution disappeared`);
          await page.goBack({waitUntil:'domcontentloaded'});
          await page.getByRole('heading',{name:'Build a living system.',exact:true}).waitFor();
        }
      } finally {await done();}
    }
  }
}
