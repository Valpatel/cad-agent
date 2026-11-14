"""Check every SCADA component's visible states in Chromium, without app CSS/JS.

Requires Python Playwright and Chromium. This complements visual screenshot
review; it checks state semantics and animation behavior, not aesthetic quality.
"""
import argparse
import hashlib
import json
import mimetypes
from pathlib import Path
import sys
from pathlib import Path
sys.path.insert(0, str((Path(__file__).resolve().parent / '../..').resolve()))
from scada_paths import REPO, UI, SIM, TOOLS, TESTS
import shutil
import sys
from urllib.parse import unquote, urlparse

from playwright.sync_api import sync_playwright
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from browser_capture import freeze_animation_frame


FIXTURE = """<!doctype html>
<html lang="en"><meta charset="utf-8">
<link rel="stylesheet" href="/styles.css">
<style>body{margin:0;background:#07131d;color:#deedf1;font:15px Arial,sans-serif}body.audit-sheet{padding:18px}h1{font-size:23px;margin:0 0 16px}.audit-row{margin:0 0 13px}.audit-row h2{font-size:16px;margin:0 0 7px;color:#d5eceb}.audit-poses{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:9px}.audit-card{height:178px;padding:7px;background:#102635;border:1px solid #355665;border-radius:9px;overflow:hidden}.audit-card>strong{display:block;min-height:24px;font-size:11px;line-height:1.3;color:#afd7d4}.audit-card .scada-component{width:100%;height:135px;max-width:100%}.audit-card .twin-equipment-art{width:100%!important;height:100%!important;max-height:100%}*,*::before,*::after{transition:none!important}</style>
<main id="fixture"></main>
<script type="module">
import * as library from '/index.mjs';
window.library = library;
// This historical contract is the original eighty types. New industrial types
// still participate in every full-catalog check below, but are not retroactive v1 members.
window.legacyTypes = new Set(library.SCADA_COMPONENTS.filter(component=>component.type!=='rack-oven'&&!['energy','electrical','nuclear','agriculture'].includes(component.drawingFamily)).map(component=>component.type));
window.auditElectricalSwitches=new Set(['breaker','hv-circuit-breaker','disconnect-switch','earthing-switch','capacitor-bank','shunt-reactor','switchgear-panel','gis-bay']);
window.auditActiveState=type=>type==='breaker'?{open:false}:type==='surge-arrester'?{stress:60}:type==='control-rod-drive'?{moving:true}:{};
window.auditSpecs=()=>library.SCADA_COMPONENTS.flatMap(component=>[{type:component.type,variant:null,descriptor:component},...library.getScadaVariants(component.type).map(variant=>({type:component.type,variant:variant.id,descriptor:library.getScadaComponent(component.type,{variant:variant.id})}))]);
window.auditVisible=element=>{for(let current=element;current;current=current.parentElement){const style=getComputedStyle(current);if(style.display==='none'||style.visibility==='hidden')return false;}return true;};
window.auditShapeSignatures=root=>[...root.querySelectorAll('svg path,svg circle,svg ellipse,svg rect,svg line,svg polyline,svg polygon,svg text')].filter(element=>!element.closest('defs,.scada-component-condition')&&auditVisible(element)).map(element=>{const m=element.getCTM();return element.outerHTML+'|'+(m?[m.a,m.b,m.c,m.d,m.e,m.f].map(value=>value.toFixed(4)).join(','):'');});
window.auditDamageEffects=(type,damage,state={},variant=null)=>{const host=document.querySelector('#fixture'),settings={id:'damage-'+type,...(variant?{variant}:{}),state:{running:false,...state}};host.innerHTML=library.renderScadaComponent(type,settings);const normal=new Set(auditShapeSignatures(host.querySelector('.scada-component')));host.innerHTML=library.renderScadaComponent(type,{...settings,state:{...settings.state,damage}});const damaged=new Set(auditShapeSignatures(host.querySelector('.scada-component')));return [...damaged].filter(signature=>!normal.has(signature)).concat([...normal].filter(signature=>!damaged.has(signature)));};
window.auditProductionSelector='.scada-industrial-machine .scada-industrial-motion,.scada-power-drive .scada-power-motion,.scada-power-combustion .scada-power-motion,.scada-electrical-flow,.scada-power-convert-pulse,.scada-power-field-pulse,.scada-power-charge,.scada-nuclear-production,.scada-nuclear-actuator,.scada-nuclear-monitor-scan,.scada-agri-motion,.scada-agri-monitor';
window.auditProductionRunning=root=>[...root.querySelectorAll(auditProductionSelector)].filter(auditVisible).flatMap(element=>element.getAnimations().filter(animation=>animation.playState==='running').map(animation=>animation.animationName));
window.renderState = state => {
  document.querySelector('#fixture').innerHTML = library.SCADA_COMPONENTS.map(
    component => library.renderScadaComponent(component.type, {
      id: 'audit-' + component.type,
      // An open breaker intentionally interrupts flow. Exercise its energized
      // state when checking that every type has useful active animation.
      state: {...auditActiveState(component.type), ...state},
    })
  ).join('');
};
window.auditPose = (component, pose) => {
  const base=component.type==='breaker'?{open:false}:{},numeric=component.stateFields.filter(field=>field.type==='number');
  if(pose==='off')return {...base,active:false};
  if(pose==='warning')return {...base,status:'warning'};
  if(pose==='damage'){const field=component.stateFields.find(field=>field.key==='damage');return {...base,...(field?{damage:field.options.find(option=>option.value!=='none').value}:{fault:true})};}
  const fraction={low:0,mid:.5,high:1}[pose];
  return {...base,...Object.fromEntries(numeric.map(field=>[field.key,field.min+(field.max-field.min)*fraction]))};
};
window.renderPoseSheet=(start,count,variants=false)=>{
  const specs=auditSpecs().filter(spec=>Boolean(spec.variant)===variants).slice(start,start+count),poses=['off','low','mid','high','warning','damage'];
  const escape=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  document.body.className='audit-sheet';
  document.querySelector('#fixture').innerHTML='<h1>SCADA '+(variants?'variant ':'')+'visual states · '+(start+1)+'–'+(start+specs.length)+'</h1>'+specs.map(({descriptor:component,variant})=>{
    const numeric=component.stateFields.filter(field=>field.type==='number');
    return '<section class="audit-row"><h2>'+escape(component.label)+' · '+escape(component.type)+(variant?' / '+escape(variant):'')+'</h2><div class="audit-poses">'+poses.map(pose=>{
      const state=auditPose(component,pose),label=pose==='damage'?'Damage: '+(state.damage??'fault'):['low','mid','high'].includes(pose)&&!numeric.length?pose+' · no numeric fields':pose;
      return '<div class="audit-card"><strong>'+escape(label)+'</strong>'+library.renderScadaComponent(component.type,{id:'pose-'+component.type+'-'+(variant??'base')+'-'+pose,...(variant?{variant}:{}),state})+'</div>';
    }).join('')+'</div></section>';
  }).join('');
  return specs.map(({descriptor:component,variant})=>({type:component.type,variant,poses:Object.fromEntries(poses.map(pose=>[pose,auditPose(component,pose)]))}));
};
renderState({});
</script></html>"""

# Chromium can report running animations inside SVG groups with display:none.
# Check visibility through the ancestor chain so hidden incident effects do not
# count as process activity. Opacity is intentionally not filtered: a visible
# pulsing effect can be at the transparent point of its cycle.
VISIBLE_ANIMATIONS = """roots => roots.map(root => ({
  type: root.dataset.scadaType,
  variant: root.dataset.scadaVariant ?? null,
  damage: root.dataset.damage,
  animations: root.getAnimations({subtree:true}).filter(animation => {
    if (animation.playState !== 'running') return false;
    let element = animation.effect.target;
    while (element && element !== root.parentElement) {
      const style = getComputedStyle(element);
      if (style.display === 'none' || style.visibility === 'hidden') return false;
      element = element.parentElement;
    }
    return true;
  }).map(animation => animation.animationName),
}))"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--static-root', type=Path, default=UI / 'src')
    parser.add_argument('--output', type=Path, default=REPO / '.cache/scada' / Path('component-states'))
    parser.add_argument('--expected-count', type=int)
    parser.add_argument('--expected-variants', type=int)
    parser.add_argument('--visual-only', action='store_true', help='Render pose sheets without running behavioral assertions.')
    args = parser.parse_args()
    root = args.static_root.resolve()
    if not (root / 'index.mjs').is_file():
        parser.error('--static-root must contain index.mjs and its dependencies')
    chromium = shutil.which('chromium')
    if not chromium:
        parser.error('Chromium is required on PATH')
    args.output.mkdir(parents=True, exist_ok=True)
    errors, missing = [], []
    served_hashes = {}
    report = {'static_root': str(root), 'states': {}}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=chromium, headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1200, 'height': 900})
        page.on('pageerror', lambda error: errors.append(str(error)))

        def serve(route):
            parsed = urlparse(route.request.url)
            if parsed.hostname != 'component-state-audit.test':
                missing.append(route.request.url)
                return route.fulfill(status=404, body='External requests are not part of this fixture')
            name = unquote(parsed.path).lstrip('/')
            if not name:
                return route.fulfill(status=200, body=FIXTURE, content_type='text/html')
            path = (root / name).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                missing.append(name)
                return route.fulfill(status=404, body='Missing standalone dependency')
            content_type = ('text/javascript' if name.endswith('.mjs') else
                            mimetypes.guess_type(name)[0] or 'application/octet-stream')
            body = path.read_bytes()
            served_hashes[name] = hashlib.sha256(body).hexdigest()
            return route.fulfill(status=200, body=body, content_type=content_type)

        page.route('**/*', serve)
        page.goto('https://component-state-audit.test/', wait_until='networkidle')
        page.wait_for_function('Boolean(window.library && window.renderState)')
        types = page.evaluate('library.SCADA_COMPONENTS.map(component => component.type)')
        assert types and len(set(types)) == len(types), types
        if args.expected_count is not None:
            assert len(types) == args.expected_count, (len(types), args.expected_count)
        report['component_count'] = len(types)
        report['variant_count'] = page.evaluate('auditSpecs().filter(spec=>spec.variant).length')
        if args.expected_variants is not None:
            assert report['variant_count'] == args.expected_variants, (report['variant_count'], args.expected_variants)
        legacy_types = set(page.evaluate('[...legacyTypes]'))
        assert len(legacy_types) == 80, 'The original 80-component motion contract must remain covered.'
        report['legacy_component_count'] = len(legacy_types)
        report['pose_sheets'] = []
        for start in range(0,len(types),8):
            pose_rows=page.evaluate('args=>renderPoseSheet(...args)',[start,8])
            page.set_viewport_size({'width':1488,'height':60+len(pose_rows)*219})
            freeze_animation_frame(page)
            assert page.evaluate('document.documentElement.scrollWidth') == 1488
            path=args.output/f'pose-sheet-{start//8+1:02}.png'
            page.screenshot(path=str(path),animations='allow',full_page=True)
            report['pose_sheets'].append({'file':path.name,'components':pose_rows})
        report['variant_pose_sheets'] = []
        for start in range(0,report['variant_count'],8):
            pose_rows=page.evaluate('args=>renderPoseSheet(...args)',[start,8,True])
            page.set_viewport_size({'width':1488,'height':60+len(pose_rows)*219})
            freeze_animation_frame(page)
            assert page.evaluate('document.documentElement.scrollWidth') == 1488
            path=args.output/f'variant-pose-sheet-{start//8+1:02}.png'
            page.screenshot(path=str(path),animations='allow',full_page=True)
            report['variant_pose_sheets'].append({'file':path.name,'components':pose_rows})
        page.set_viewport_size({'width':1200,'height':900})
        page.evaluate("document.body.className=''")
        if args.visual_only:
            assert not errors and not missing, (errors,missing)
            (args.output/'component-poses.json').write_text(json.dumps(report,indent=2)+'\n')
            browser.close()
            print(json.dumps({'components':len(types),'variants':report['variant_count'],'pose_sheets':len(report['pose_sheets'])+len(report['variant_pose_sheets']),'errors':errors}))
            return

        states = (
            ('active', {}),
            ('off', {'active': False}),
            ('paused', {'running': False}),
            ('offline', {'status': 'offline'}),
            ('fault-paused', {'fault': True, 'running': False}),
        )
        for name, state in states:
            page.evaluate('(state) => renderState(state)', state)
            animations = page.locator('.scada-component').evaluate_all(VISIBLE_ANIMATIONS)
            report['states'][name] = animations
            if name == 'active':
                # An earthing blade has actual commanded geometry, not a
                # fictional continuous current or idle spinning mechanism.
                static_types = {'earthing-switch'}
                assert all(item['animations'] or item['type'] in static_types for item in animations), animations
                advances=page.locator('.scada-component').evaluate_all("""async roots=>{
                  const rows=roots.map(root=>({type:root.dataset.scadaType,animations:root.getAnimations({subtree:true}).filter(animation=>animation.playState==='running')}));
                  const before=rows.map(row=>row.animations.map(animation=>Number(animation.currentTime)));
                  await new Promise(resolve=>setTimeout(resolve,200));
                  return rows.map((row,i)=>({type:row.type,advanced:row.animations.some((animation,j)=>Number(animation.currentTime)-before[i][j]>80)}));
                }""")
                assert all(item['advanced'] or item['type'] in static_types for item in advances), advances
                report['actual_animation_clocks']=advances
            elif name == 'off':
                assert not any(item['animations'] for item in animations if item['type'] in legacy_types), (name, animations)
                stopped = page.locator('.scada-component').evaluate_all('roots=>roots.map(root=>({type:root.dataset.scadaType,production:auditProductionRunning(root)}))')
                assert not any(item['production'] for item in stopped), stopped
                report['source_off_production'] = stopped
            else:
                assert not any(item['animations'] for item in animations), (name, animations)

        # Fault effects may remain animated, but rotors, flow and scan activity
        # must stop. These four animation families are explicit fault cues.
        page.evaluate('renderState({fault:true})')
        allowed_fault_motion = {
            'scada-fault', 'twin-art-fault-breathe',
            'twin-art-sparks', 'twin-art-smoke-drift',
        }
        fault_motion = page.locator('.scada-component').evaluate_all(VISIBLE_ANIMATIONS)
        assert all(set(item['animations']) <= allowed_fault_motion for item in fault_motion if item['type'] in legacy_types), fault_motion
        stopped = page.locator('.scada-component').evaluate_all('roots=>roots.map(root=>({type:root.dataset.scadaType,production:auditProductionRunning(root)}))')
        assert not any(item['production'] for item in stopped), stopped
        assert page.locator('.scada-component[data-active="false"]').count() == len(types)
        report['states']['fault'] = fault_motion

        for cue, state in (
            ('warning', {'status': 'warning', 'running': False}),
            ('fault', {'fault': True, 'running': False}),
        ):
            page.evaluate('(state) => renderState(state)', state)
            assert page.locator(f'[data-condition="{cue}"]:visible').count() == len(types)
            assert page.locator('.scada-component').evaluate_all("""roots => roots.every(root =>
              root.getAttribute('aria-label').toLowerCase().includes(
                root.querySelector('[data-condition]').dataset.condition))""")
        report['warning_and_fault_cues'] = 'Visible and accessible for every type'

        # Every connectivity field and open/closed path is checked according to
        # its declared type. No undeclared field is passed to another component.
        report['connections'] = page.evaluate("""() => {
          const results = [];
          for (const component of library.SCADA_COMPONENTS) {
            const fields = new Set(component.stateFields.map(field => field.key));
            if (!fields.has('connected') && !fields.has('open')) continue;
            const host = document.querySelector('#fixture');
            const state = fields.has('connected') ? {connected:false} :
              {open:auditElectricalSwitches.has(component.type)};
            host.innerHTML = library.renderScadaComponent(component.type, {state});
            const root = host.querySelector('.scada-component');
            if (root.dataset.flow !== 'false') throw Error(component.type + ' still shows a flow path');
            if (fields.has('connected') && root.dataset.active !== 'false')
              throw Error(component.type + ' still active when disconnected');
            results.push({type:component.type, state});
          }
          return results;
        }""")

        # Every declared numeric field is tested at its low/mid/high limit;
        # gauge values and normalized bars must follow the actual input.
        report['numeric_readouts'] = page.evaluate("""() => {
          const results=[],host=document.querySelector('#fixture');
          for(const spec of auditSpecs()){
            const component=spec.descriptor,options=spec.variant?{variant:spec.variant}:{};
            for(const field of component.stateFields.filter(field=>field.type==='number')){
              const values=[];
              for(const fraction of [0,.5,1]){
                const value=field.min+(field.max-field.min)*fraction;
                host.innerHTML=library.renderScadaComponent(component.type,{id:'numeric-'+component.type,...options,state:{[field.key]:value,running:false}});
                const root=host.querySelector('.scada-component'),reading=root.querySelector('[data-scada-reading="'+field.key+'"]'),bar=root.querySelector('[data-scada-gauge="'+field.key+'"] b');
                if(!reading||!bar)throw Error(component.type+'/'+field.key+' lacks a keyed value/bar');
                const numeric=Number(reading.textContent.match(/[-+]?\\d+(?:\\.\\d+)?/)?.[0]);
                if(!Number.isFinite(numeric)||Math.abs(numeric-Number(value.toFixed(1)))>.001)throw Error(component.type+'/'+field.key+' reading mismatch: '+reading.textContent);
                if(Math.abs(parseFloat(bar.style.width)-fraction*100)>.001)throw Error(component.type+'/'+field.key+' bar mismatch');
                if(!root.getAttribute('aria-label').includes('illustrative '+field.key+' '+value))throw Error(component.type+'/'+field.key+' accessible reading missing');
                const svg=[...root.querySelectorAll('svg')].filter(el=>!el.closest('.scada-component-condition')).map(el=>el.innerHTML).join('');
                const visual=[...root.querySelectorAll('svg path,svg rect,svg circle,svg ellipse,svg line,svg polyline,svg polygon,svg text,svg g')].filter(el=>!el.closest('defs,.scada-component-condition')).map(el=>{const style=getComputedStyle(el);return [el.getAttribute('class'),style.opacity,style.fill,style.stroke,style.strokeWidth,style.transform,style.translate,style.scale,style.filter,style.width,style.height,style.animationDuration,style.visibility,style.display].join('|')}).join(';');
                values.push({fraction,value,reading:reading.textContent,bar:bar.style.width,svg,visual});
              }
              const geometryChanges=values[0].svg!==values[2].svg;
              results.push({type:component.type,variant:spec.variant,field:field.key,values:values.map(({svg,visual,...item})=>item),geometryChanges,visualChanges:geometryChanges||values[0].visual!==values[2].visual});
            }
          }
          return results;
        }""")

        report['valve_aperture'] = page.evaluate("""() => {
          const host=document.querySelector('#fixture'),results=[];
          for(const type of ['control-valve','gate-valve','butterfly-valve']){
            const samples=[0,50,100].map(opening=>{
              host.innerHTML=library.renderScadaComponent(type,{id:'aperture-'+type,state:{opening,running:false}});
              const root=host.querySelector('.scada-component');
              if(root.dataset.opening!==String(opening))throw Error(type+' opening attribute mismatch');
              if(root.dataset.flow!==String(opening>0))throw Error(type+' flow does not follow aperture');
              return {opening,geometry:root.querySelector('svg').innerHTML};
            });
            if(new Set(samples.map(item=>item.geometry)).size!==3)throw Error(type+' aperture does not interpolate actual SVG geometry');
            host.innerHTML=library.renderScadaComponent(type,{id:'aperture-'+type,state:{opening:75,open:false,running:false}});
            if(host.querySelector('.scada-component').dataset.opening!=='0')throw Error(type+' boolean closure must override aperture');
            results.push({type,openings:samples.map(({opening})=>opening),distinctGeometry:true,booleanClosure:true});
          }
          return results;
        }""")

        # A speed field must control real driven motion, not only its gauge.
        report['speed_motion']=page.evaluate("""() => {
          const host=document.querySelector('#fixture'),results=[];
          const driven='.scada-rotor,.scada-piston,.scada-shaft,.scada-flow,.twin-art-rotor,.twin-art-stream,.twin-art-generator-current,.scada-process-flow,.scada-process-rotor,.scada-process-wind-rotor,.scada-process-drum,.scada-process-agitator,.scada-industrial-machine .scada-industrial-motion,.scada-power-drive .scada-power-motion,.scada-nuclear-actuator';
          const visible=element=>{for(let current=element;current&&current!==host;current=current.parentElement){const style=getComputedStyle(current);if(style.display==='none'||style.visibility==='hidden')return false;}return true;};
          for(const spec of auditSpecs().filter(spec=>spec.descriptor.stateFields.some(field=>field.key==='speed'))){
            const component=spec.descriptor,options=spec.variant?{variant:spec.variant}:{};
            const sample=speed=>{
              host.innerHTML=library.renderScadaComponent(component.type,{id:'speed-'+component.type,...options,state:{...auditActiveState(component.type),speed}});
              const root=host.querySelector('.scada-component');
              return [...root.querySelectorAll(driven)].filter(visible).flatMap(element=>element.getAnimations().filter(animation=>animation.playState==='running').map(animation=>({key:element.getAttribute('class')+'|'+animation.animationName,duration:Number(animation.effect.getComputedTiming().duration)})));
            };
            const slow=sample(25),fast=sample(75),stopped=sample(0);
            const faster=fast.some(item=>slow.some(previous=>previous.key===item.key&&previous.duration>item.duration));
            results.push({type:component.type,variant:spec.variant,slow,fast,zeroDrivenAnimations:stopped.length,
              errors:[...(stopped.length?['Driven motion continues at speed0: '+stopped.map(item=>item.key).join(',')]:[]),...(!faster?['Speed does not change a driven animation duration']:[])]});
          }
          return results;
        }""")
        speed_errors = [item for item in report['speed_motion'] if item['errors']]
        if speed_errors:
            (args.output / 'speed-motion-failures.json').write_text(json.dumps(speed_errors, indent=2) + '\n')
            raise AssertionError('Speed motion: ' + '; '.join(item['type'] + ': ' + ', '.join(item['errors']) for item in speed_errors))

        # Sample real browser animation clocks at both speeds. CSS duration
        # alone cannot prove an animation is actually progressing on screen.
        report['actual_speed_cadence']=page.evaluate("""async () => {
          const host=document.querySelector('#fixture'),results=[];
          const driven='.scada-rotor,.scada-piston,.scada-shaft,.scada-flow,.twin-art-rotor,.twin-art-stream,.twin-art-generator-current,.scada-process-flow,.scada-process-rotor,.scada-process-wind-rotor,.scada-process-drum,.scada-process-agitator,.scada-industrial-machine .scada-industrial-motion,.scada-power-drive .scada-power-motion,.scada-nuclear-actuator';
          for(const spec of auditSpecs().filter(spec=>spec.descriptor.stateFields.some(field=>field.key==='speed'))){
            host.innerHTML=[25,75].map(speed=>library.renderScadaComponent(spec.type,{id:'cadence-'+spec.type+'-'+speed,...(spec.variant?{variant:spec.variant}:{}),state:{...auditActiveState(spec.type),speed}})).join('');
            const roots=[...host.querySelectorAll('.scada-component')];
            const rows=roots.map(root=>[...root.querySelectorAll(driven)].filter(auditVisible).flatMap(element=>element.getAnimations().filter(animation=>animation.playState==='running').map(animation=>({animation,key:element.getAttribute('class')+'|'+animation.animationName}))));
            await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
            for(const row of rows.flat())row.before=Number(row.animation.currentTime);
            const began=performance.now();
            await new Promise(resolve=>setTimeout(resolve,160));
            const elapsed=performance.now()-began;
            const samples=rows.map(row=>row.map(({animation,key,before})=>{const milliseconds=Number(animation.currentTime)-before;return {key,milliseconds,cyclesPerSecond:milliseconds/Number(animation.effect.getComputedTiming().duration)/(elapsed/1000)}}));
            const advancing=samples.every(sample=>sample.some(item=>item.milliseconds>60));
            const faster=samples[1].some(fast=>samples[0].some(slow=>slow.key===fast.key&&fast.cyclesPerSecond>slow.cyclesPerSecond*1.05));
            if(!advancing||!faster)throw Error(spec.type+'/'+(spec.variant??'base')+' does not advance faster at higher speed');
            results.push({type:spec.type,variant:spec.variant,elapsed,slow:samples[0],fast:samples[1],advancing,faster});
          }
          return results;
        }""")

        # Every declared damage mode must produce physical SVG geometry and an
        # accessible description, independently of the generic fault badge.
        report['damage_modes']=page.evaluate("""() => {
          const results=[],host=document.querySelector('#fixture');
          const visible=element=>{let node=element;while(node&&node!==host){const style=getComputedStyle(node);if(style.display==='none'||style.visibility==='hidden')return false;node=node.parentElement;}return true;};
          for(const spec of auditSpecs()){
            const component=spec.descriptor;
            const field=component.stateFields.find(field=>field.key==='damage');
            if(!field)throw Error(component.type+' has no declared damage state');
            for(const option of field.options.filter(option=>option.value!=='none')){
              const effects=auditDamageEffects(component.type,option.value,{},spec.variant);
              const root=host.querySelector('.scada-component');
              if(root.dataset.damage!==option.value)throw Error(component.type+' damage attribute mismatch');
              if(!root.getAttribute('aria-label').includes('damage: '+option.value.replaceAll('-',' ')))throw Error(component.type+' damage description missing');
              if(!effects.length)throw Error(component.type+'/'+option.value+' has no visible physical damage geometry');
              if(root.getAnimations({subtree:true}).some(animation=>animation.playState==='running'&&visible(animation.effect.target)))throw Error(component.type+'/'+option.value+' animates while paused');
              results.push({type:component.type,variant:spec.variant,damage:option.value,visibleGeometry:effects.length});
            }
          }
          return results;
        }""")

        # Every declared incident is frozen by offline, user pause and reduced
        # motion. A source being off is a different state: leaks, ambient waves
        # and retained thermal conditions can legitimately remain visible.
        page.evaluate("""window.renderDamageState=state=>{
          document.querySelector('#fixture').innerHTML=auditSpecs().flatMap(spec=>spec.descriptor.stateFields.find(field=>field.key==='damage').options.filter(option=>option.value!=='none').map(option=>library.renderScadaComponent(spec.type,{id:'incident-'+spec.type+'-'+(spec.variant??'base')+'-'+option.value,...(spec.variant?{variant:spec.variant}:{}),state:{damage:option.value,...state}}))).join('');
        }""")
        page.evaluate("renderDamageState({status:'offline'})")
        offline_incidents=page.locator('.scada-component').evaluate_all(VISIBLE_ANIMATIONS)
        offline_failures=[item for item in offline_incidents if item['animations']]
        if offline_failures:
            (args.output/'offline-incident-failures.json').write_text(json.dumps(offline_failures,indent=2)+'\n')
        assert not offline_failures, ('Offline incidents still moving',offline_failures)
        page.evaluate("renderDamageState({});document.documentElement.classList.add('motion-paused')")
        assert not any(item['animations'] for item in page.locator('.scada-component').evaluate_all(VISIBLE_ANIMATIONS))
        page.evaluate("document.documentElement.classList.remove('motion-paused')")
        page.emulate_media(reduced_motion='reduce')
        assert not any(item['animations'] for item in page.locator('.scada-component').evaluate_all(VISIBLE_ANIMATIONS))
        report['reduced_damage_geometry']=page.evaluate("""() => {
          const results=[];
          for(const spec of auditSpecs())for(const option of spec.descriptor.stateFields.find(field=>field.key==='damage').options.filter(option=>option.value!=='none')){
            const component=spec.descriptor,effects=auditDamageEffects(component.type,option.value,{},spec.variant);
            if(!effects.length)throw Error(component.type+'/'+option.value+' loses physical damage in reduced motion');
            results.push({type:component.type,variant:spec.variant,damage:option.value,visibleGeometry:effects.length});
          }
          return results;
        }""")
        page.emulate_media(reduced_motion='no-preference')
        report['all_incident_pause_modes']={'damageCases':len(report['damage_modes']),'offline':True,'globalPause':True,'reducedMotion':True}

        # Explicit variants use their resolved declarations and the same state
        # gates. In particular a portable genset cannot inherit a hidden twin
        # rotor or ignore paused/offline state.
        report['variant_states']=page.evaluate("""() => {
          const host=document.querySelector('#fixture'),results=[];
          for(const spec of auditSpecs().filter(item=>item.variant)){
            const states=[];
            for(const [name,patch] of Object.entries({active:{},off:{active:false},paused:{running:false},offline:{status:'offline'},fault:{fault:true},faultPaused:{fault:true,running:false}})){
              host.innerHTML=library.renderScadaComponent(spec.type,{variant:spec.variant,state:{...auditActiveState(spec.type),...patch}});
              const root=host.querySelector('.scada-component'),running=root.getAnimations({subtree:true}).filter(animation=>animation.playState==='running'&&auditVisible(animation.effect.target));
              if(root.dataset.scadaVariant!==spec.variant)throw Error(spec.type+'/'+spec.variant+' lost explicit variant identity');
              if(name==='active'&&!running.length)throw Error(spec.type+'/'+spec.variant+' has no visible active motion');
              if(['paused','offline','faultPaused'].includes(name)&&running.length)throw Error(spec.type+'/'+spec.variant+' moves during '+name);
              if(['off','fault'].includes(name)&&auditProductionRunning(root).length)throw Error(spec.type+'/'+spec.variant+' still produces during '+name);
              if(name==='off'&&legacyTypes.has(spec.type)&&running.length)throw Error(spec.type+'/'+spec.variant+' changed legacy off behavior');
              if(!root.getAttribute('aria-label').includes(spec.descriptor.label))throw Error(spec.type+'/'+spec.variant+' has stale accessible label');
              states.push({name,animations:running.map(animation=>animation.animationName)});
            }
            results.push({type:spec.type,variant:spec.variant,states});
          }
          return results;
        }""")

        report['variant_animation_clocks']=page.evaluate("""async () => {
          const host=document.querySelector('#fixture'),specs=auditSpecs().filter(spec=>spec.variant);
          host.innerHTML=specs.map(spec=>library.renderScadaComponent(spec.type,{variant:spec.variant,state:auditActiveState(spec.type)})).join('');
          const rows=[...host.querySelectorAll('.scada-component')].map(root=>({type:root.dataset.scadaType,variant:root.dataset.scadaVariant,animations:root.getAnimations({subtree:true}).filter(animation=>animation.playState==='running'&&auditVisible(animation.effect.target))}));
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
          const before=rows.map(row=>row.animations.map(animation=>Number(animation.currentTime)));
          await new Promise(resolve=>setTimeout(resolve,180));
          const results=rows.map((row,i)=>({type:row.type,variant:row.variant,advanced:row.animations.some((animation,j)=>Number(animation.currentTime)-before[i][j]>70)}));
          for(const row of results)if(!row.advanced)throw Error(row.type+'/'+row.variant+' active clock did not advance');
          return results;
        }""")

        report['independent_layers']=page.evaluate("""async () => {
          const host=document.querySelector('#fixture'),results=[];
          const sample=(type,state)=>{host.innerHTML=library.renderScadaComponent(type,{id:'independent-'+type,state});return host.querySelector('.scada-component')};
          const animations=(root,selector)=>[...root.querySelectorAll(selector)].filter(auditVisible).flatMap(el=>el.getAnimations().filter(a=>a.playState==='running'));
          let root=sample('pwr-reactor-vessel',{active:false,fault:true,load:0,heat:70,flow:40,damage:'leaking'});
          for(const selector of ['.scada-nuclear-primary','.scada-nuclear-residual','.scada-nuclear-drip']){
            const motion=animations(root,selector),before=motion.map(a=>Number(a.currentTime));
            if(!motion.length)throw Error('Shutdown PWR loses supplied layer '+selector);
            await new Promise(resolve=>setTimeout(resolve,120));
            if(!motion.some((a,i)=>Number(a.currentTime)-before[i]>50))throw Error('PWR retained layer clock did not advance: '+selector);
            results.push({type:'pwr-reactor-vessel',layer:selector,continuesAfterSourceStops:true});
          }
          if(auditProductionRunning(root).length)throw Error('Shutdown PWR source/actuator still producing');
          root=sample('pwr-reactor-vessel',{active:false,load:0,heat:0,flow:0,damage:'none'});
          if(root.getAnimations({subtree:true}).some(a=>a.playState==='running'&&auditVisible(a.effect.target)))throw Error('Cold-off PWR still moves');
          for(const primary of [0,60]){
            root=sample('nuclear-steam-generator',{primaryFlow:primary,secondaryFlow:primary?0:60});
            if(Boolean(animations(root,'.scada-nuclear-primary').length)!==Boolean(primary)||Boolean(animations(root,'.scada-nuclear-secondary').length)===Boolean(primary))throw Error('Steam-generator circuits are not independent');
          }
          results.push({type:'nuclear-steam-generator',separatePrimaryAndSecondary:true});
          root=sample('control-rod-drive',{rodPosition:30,moving:false,speed:60});
          if(animations(root,'.scada-nuclear-actuator').length)throw Error('Held rod drive moves');
          root=sample('control-rod-drive',{rodPosition:30,moving:true,speed:60,damage:'jammed'});
          if(animations(root,'.scada-nuclear-actuator').length)throw Error('Jammed rod drive moves');
          for(const type of ['neutron-monitor','radiation-monitor'])for(const state of [{active:false},{connected:false},{fault:true},{status:'offline'},{damage:'broken'},{damage:'disconnected'}]){
            root=sample(type,state);
            if([...root.querySelectorAll('.scada-nuclear-readout,[data-scada-reading]')].some(el=>el.textContent!=='—'))throw Error(type+' shows an unqualified invalid index');
          }
          results.push({type:'nuclear-monitors',invalidReadingsSuppressed:true});
          root=sample('fish-tank',{active:false,fault:true,damage:'leaking'});
          if(!animations(root,'.scada-agri-incident').length||auditProductionRunning(root).length)throw Error('Stopped fish-tank must retain leak but stop driven activity');
          results.push({type:'fish-tank',leakIndependentFromSource:true});
          return results;
        }""")

        # A failed hot machine stops producing while its visible incident still
        # moves; global pause and accessibility preferences stop both layers.
        page.evaluate("document.querySelector('#fixture').innerHTML=library.renderScadaComponent('rotary-kiln',{id:'incident-kiln',state:{fault:true,damage:'overheated'}})")
        report['incident_motion'] = page.locator('.scada-component').evaluate("""async root=>{
          const production=[...root.querySelectorAll('.scada-industrial-machine')].flatMap(element=>element.getAnimations({subtree:true})).filter(animation=>animation.playState==='running');
          const incident=[...root.querySelectorAll('.scada-industrial-overheat')].flatMap(element=>element.getAnimations({subtree:true})).filter(animation=>animation.playState==='running');
          if(production.length||!incident.length)throw Error('Faulted hot kiln must stop production but retain heat incident motion');
          const before=incident.map(animation=>Number(animation.currentTime));
          await new Promise(resolve=>setTimeout(resolve,180));
          const advanced=incident.some((animation,i)=>Number(animation.currentTime)-before[i]>80);
          if(!advanced)throw Error('Heat incident clock did not advance');
          return {productionAnimations:production.length,incidentAnimations:incident.length,actualHeatMotion:advanced};
        }""")
        page.evaluate("document.documentElement.classList.add('motion-paused')")
        assert not any(item['animations'] for item in page.locator('.scada-component').evaluate_all(VISIBLE_ANIMATIONS))
        page.evaluate("document.documentElement.classList.remove('motion-paused')")
        page.emulate_media(reduced_motion='reduce')
        assert not any(item['animations'] for item in page.locator('.scada-component').evaluate_all(VISIBLE_ANIMATIONS))
        page.emulate_media(reduced_motion='no-preference')

        page.evaluate('renderState({fault:true})')
        page.emulate_media(reduced_motion='reduce')
        assert page.locator('#fixture').evaluate("""root => root.getAnimations({subtree:true})
          .filter(animation => animation.playState === 'running').length""") == 0
        report['reduced_motion'] = 'All animations stopped, including fault effects'
        page.emulate_media(reduced_motion='no-preference')

        # This catches a regression where a standalone default on the nested
        # wrapper shadowed the live twin's inventory CSS variable.
        page.locator('#fixture').evaluate("""host => {
          host.innerHTML = '<div class="twin-node" style="--buffer-fraction:.23" data-active="true">' +
            library.renderScadaComponent('gas-holder', {
              id:'host-buffer', hostState:true, decorative:true,
            }) + '</div>';
        }""")
        assert page.locator('.scada-component').get_attribute('style') is None
        fill = page.locator('.twin-art-buffer-fill').evaluate("""element => ({
          fraction:getComputedStyle(element).getPropertyValue('--buffer-fraction'),
          scaleY:new DOMMatrix(getComputedStyle(element).transform).m22,
        })""")
        assert fill['fraction'] == '.23' and abs(fill['scaleY'] - .23) < .0001, fill
        report['host_buffer_inheritance'] = fill

        # Several instances of every type must resolve all local SVG resources
        # without clobbering another illustration's definitions.
        report['namespaces'] = page.evaluate("""() => {
          const host = document.querySelector('#fixture');
          const specs=auditSpecs();
          host.innerHTML = specs.map(spec => {
            const options=spec.variant?{variant:spec.variant}:{};
            return library.renderScadaComponent(spec.type,options)+library.renderScadaComponent(spec.type,options);
          }).join('');
          const ids = [...host.querySelectorAll('[id]')].map(element => element.id);
          if (ids.length !== new Set(ids).size) throw Error('Duplicate generated SVG IDs');
          let references = 0;
          for (const root of host.querySelectorAll('.scada-component')) {
            const local = new Set([...root.querySelectorAll('[id]')].map(element => element.id));
            for (const element of root.querySelectorAll('*')) for (const attribute of element.attributes) {
              for (const match of attribute.value.matchAll(/url\\(#([^)]*)\\)/g)) {
                if (!local.has(match[1])) throw Error('Missing local SVG reference: ' + match[1]);
                references++;
              }
            }
          }
          let rejectsDot = false;
          try { library.renderScadaComponent('pump', {id:'a.b'}); }
          catch { rejectsDot = true; }
          if (!rejectsDot) throw Error('Dot IDs can collide with legacy artwork dash normalization');
          return {instances:specs.length * 2, unique_ids:ids.length, local_references:references};
        }""")

        assert not errors, errors
        assert not missing, missing
        assert served_hashes == {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in served_hashes}, 'Source changed during the audit; rerun against the final source.'
        report['source_hashes'] = served_hashes
        report['runtime_errors'], report['missing_dependencies'] = errors, missing
        browser.close()

    (args.output / 'component-states.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({
        'components': report['component_count'],
        'numeric_readouts': len(report['numeric_readouts']),
        'damage_modes': len(report['damage_modes']),
        'variants': len(report['variant_states']),
        'pose_sheets': len(report['pose_sheets']),
        'variant_pose_sheets': len(report['variant_pose_sheets']),
        'actual_speed_cadence': len(report['actual_speed_cadence']),
        'states': 'active, off, paused, offline, fault, warning, disconnected, open/closed',
        'reduced_motion': True,
        'host_buffer_scale': report['host_buffer_inheritance']['scaleY'],
        'result': str(args.output / 'component-states.json'),
    }, indent=2))


if __name__ == '__main__':
    main()
