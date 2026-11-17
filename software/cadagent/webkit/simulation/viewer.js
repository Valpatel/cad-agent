/** Recorded simulation adapter: shared host, stage, camera gestures and theme; no physics backend. */
import {createViewerHost} from '../host/viewer-host.js';
import {bindStageControls,captureCamera,restoreCamera,validateCamera} from '../host/stage-controls.js';
import {createStage} from '../model/stage.js';
import {createPlayback,loadMeshLibrary,loadRecording,validateRecording} from './replay.js';
import {createPoseScene} from './scene.js';

const el=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};

/** Mount into a connected, sized container. Supply one recording (data or a same-origin URL), or `scenarios`:
 * [{id, label, recording | recordingUrl, expectedHash, summary}] chosen in the viewer, with an optional mesh library
 * (`meshes`, already loaded, or `meshesUrl` + `meshesHash`). A summary is shown as its source's own text.
 * `autoplay` starts playback once the view is ready, except under prefers-reduced-motion; `loop` repeats it. */
export function createReplayViewer(container,{recording,recordingUrl,expectedHash,scenarios,meshes,meshesUrl,meshesHash,initialScenario,autoplay=false,loop=false,title='Recorded simulation replay',signal}={}) {
  const choices=(scenarios??[{id:'recording',label:title,recording,recordingUrl,expectedHash,summary:null}]).map(s=>({...s}));
  if(!choices.length||new Set(choices.map(s=>s.id)).size!==choices.length)throw new TypeError('Replay scenarios need unique IDs');
  let controller,scene,stage,chooser,active=choices.find(s=>s.id===initialScenario)??choices[0],select;
  const host=createViewerHost(container,{title,signal,async mount({viewport,inspector,signal,onProgress,onState}){
    onProgress(meshesUrl?'Loading recorded shapes…':'Checking recorded poses…');
    const library=meshes??(meshesUrl?await loadMeshLibrary(meshesUrl,{signal,expectedHash:meshesHash}):null);
    signal.throwIfAborted();
    const cache=new Map(),load=async choice=>{
      if(!cache.has(choice.id))cache.set(choice.id,(choice.recording?Promise.resolve(validateRecording(choice.recording,{parts:library??undefined})):loadRecording(choice.recordingUrl,{signal,expectedHash:choice.expectedHash,parts:library??undefined}))
        .catch(error=>{cache.delete(choice.id);throw error;}));
      return cache.get(choice.id);
    };
    onProgress('Checking recorded poses…');
    let data=await load(active);
    signal.throwIfAborted();
    const root=viewport.closest('.cad-viewer-host'),controls=el('div'),summary=el('div'),summarised=choices.some(c=>c.summary);controls.className='replay-controls';summary.className='replay-summary';
    root.classList.add('cad-replay-host');root.classList.toggle('cad-replay-summarised',summarised);root.insertBefore(controls,viewport.parentElement);if(summarised)root.insertBefore(summary,viewport.parentElement.nextSibling);
    const events=new AbortController(),system=matchMedia('(prefers-color-scheme: dark)');
    let unbind,offFrame,ownedScene,ownedStage,ownedClock,disposed=false,switching=0;
    const dispose=()=>{
      if(disposed)return;disposed=true;events.abort();system.removeEventListener('change',palette);signal.removeEventListener('abort',dispose);
      offFrame?.();unbind?.();ownedClock?.dispose();ownedScene?.dispose();ownedStage?.dispose();controls.remove();summary.remove();
      if(controller===ownedClock){controller=scene=stage=null;}
    };
    const palette=()=>{
      if(!ownedStage||disposed)return;
      const css=getComputedStyle(root),value=name=>css.getPropertyValue(name).trim();
      ownedStage.setPalette({background:value('--viewer-bg'),accent:value('--viewer-accent'),grid:value('--viewer-line'),glow:value('--viewer-accent')});
    };
    signal.addEventListener('abort',dispose,{once:true});
    try{
      ownedStage=createStage(viewport,{height:1,onError:error=>onState({state:'error',message:error.message})});stage=ownedStage;
      const play=el('button','Play'),restart=el('button','Restart'),timeLabel=el('label','Time'),time=el('input'),speedLabel=el('label','Speed'),speed=el('select'),readout=el('output');
      play.type=restart.type='button';play.setAttribute('aria-label','Play recording');restart.setAttribute('aria-label','Restart recording');
      time.type='range';time.min='0';time.step='.001';time.value='0';time.setAttribute('aria-label','Recording time');
      timeLabel.className='replay-time';timeLabel.append(time);
      speed.setAttribute('aria-label','Playback speed');for(const n of [.25,.5,1,2]){const option=el('option',`${n}×`);option.value=n;option.selected=n===1;speed.append(option);}speedLabel.append(speed);
      readout.className='replay-readout';readout.setAttribute('aria-label','Recorded time');
      if(choices.length>1){
        const label=el('label','Scenario');label.className='replay-scenario';select=el('select');select.setAttribute('aria-label','Scenario');
        for(const choice of choices){const option=el('option',choice.label);option.value=choice.id;select.append(option);}
        select.value=active.id;label.append(select);controls.append(label);
      }
      controls.append(play,restart,timeLabel,readout,speedLabel);
      const heading=el('h3','Recorded evidence'),description=el('p'),list=el('ul');
      const limits=el('p','Playback interpolates a completed solver run. Changing speed or time does not change forces or recompute dynamics.');
      inspector.append(heading,description,list,limits);
      const showSummary=()=>{
        const s=active.summary;summary.replaceChildren();if(!s){summary.append(el('p','No summary was recorded for this scenario.'));return;}
        const head=el('p'),badge=el('strong',s.verdict.label);badge.className='replay-verdict';badge.dataset.pass=String(s.verdict.pass);
        head.append(el('span',`${s.title}: `),badge);if(s.verdict.reasons.length)head.append(el('span',` (${s.verdict.reasons.join('; ')})`));
        const values=el('dl');for(const m of s.metrics){const row=el('div');row.append(el('dt',m.label),el('dd',m.value));values.append(row);}
        const note=el('p',s.note);note.className='replay-summary-note';summary.append(head,values,note);
      };
      const describe=()=>{
        description.textContent=`${data.bodies.length} bodies · ${data.frames.length} captured frames · ${data.duration.toFixed(2)} seconds.`;
        list.replaceChildren(...data.bodies.map(body=>el('li',body.label)));showSummary();
      };
      const build=()=>{
        ownedScene=createPoseScene(ownedStage,data,{meshes:library});scene=ownedScene;ownedStage.frame(ownedScene.height);
        // A followed robot is framed by its own size, not by the metres it drives.
        if(ownedScene.reach)ownedStage.controls.minDistance=Math.min(ownedStage.controls.minDistance,ownedScene.reach);
        time.max=String(data.duration);
        ownedClock=createPlayback(data,(state,poses)=>{
          ownedScene.apply(poses);time.value=String(state.time);time.setAttribute('aria-valuetext',`${state.time.toFixed(2)} of ${state.duration.toFixed(2)} seconds`);
          readout.textContent=`${state.time.toFixed(2)} / ${state.duration.toFixed(2)} s`;
          play.textContent=state.playing?'Pause':'Play';play.setAttribute('aria-label',state.playing?'Pause recording':'Play recording');play.setAttribute('aria-pressed',String(state.playing));
          let custom=speed.querySelector('[data-custom-speed]');
          if(![.25,.5,1,2].includes(state.speed)){if(!custom){custom=el('option');custom.dataset.customSpeed='true';speed.append(custom);}custom.value=String(state.speed);custom.textContent=`${state.speed}×`;}
          else custom?.remove();
          speed.value=String(state.speed);
          onState({state:'ready',playback:state});
        },{loop});controller=ownedClock;describe();ownedScene.fit();
      };
      build();
      const listen=(node,type,fn)=>node.addEventListener(type,fn,{signal:events.signal});
      listen(play,'click',()=>ownedClock.state().playing?ownedClock.pause():ownedClock.play());
      listen(restart,'click',()=>{ownedClock.pause();ownedClock.seek(0);});
      // A range snaps to its step, so a duration that is not a whole number of steps tops out short: the last step means the end.
      listen(time,'input',()=>{const end=ownedClock.state().duration,requested=+time.value>end-(+time.step||0)?end:+time.value;ownedClock.pause();ownedClock.seek(requested);});
      listen(speed,'change',()=>ownedClock.setSpeed(+speed.value));
      listen(document,'visibilitychange',()=>{if(document.hidden)ownedClock.pause();});
      listen(document,'cad-themechange',palette);system.addEventListener('change',palette);palette();
      // Switching keeps the stage, its camera gestures and the playback speed; the latest choice wins a race.
      const choose=async id=>{
        const choice=choices.find(s=>s.id===id);if(!choice)throw new TypeError(`Unknown scenario ${id}`);
        const request=++switching,{speed:keepSpeed,playing:wasPlaying}=ownedClock.state();ownedClock.pause();
        if(select){select.value=id;select.disabled=true;}
        try{
          const next=await load(choice);if(disposed||request!==switching)return false;
          ownedClock.dispose();ownedScene.dispose();active=choice;data=next;build();ownedClock.setSpeed(keepSpeed);if(wasPlaying)ownedClock.play();
          return true;
        }catch(error){if(select)select.value=active.id;onState({state:'error',message:error.message});throw error;}
        finally{if(select&&request===switching)select.disabled=false;}
      };
      chooser=choose;if(select)listen(select,'change',()=>{choose(select.value).catch(()=>{});});
      const selection=root.querySelector('.cad-viewer-selection');selection.textContent='Drag to orbit · two fingers to pan/zoom · Home to fit';selection.removeAttribute('aria-live');
      unbind=bindStageControls(viewport,ownedStage,()=>ownedScene.fit());
      offFrame=ownedStage.onFrame((_,dt)=>ownedClock.advance(dt));ownedStage.start();
      if(autoplay&&!matchMedia('(prefers-reduced-motion: reduce)').matches)ownedClock.play();
      const documentId=crypto.randomUUID();
      return {fit:()=>ownedScene.fit(),choose,
        getViewState:()=>({version:1,kind:'recorded-simulation',documentId,scenario:active.id,camera:captureCamera(ownedStage),time:ownedClock.state().time,speed:ownedClock.state().speed}),
        restoreViewState(value){
          if(!value||value.version!==1||value.kind!=='recorded-simulation'||value.documentId!==documentId||(value.scenario!==undefined&&value.scenario!==active.id)||!Number.isFinite(value.time)||value.time<0||value.time>data.duration||!Number.isFinite(value.speed)||value.speed<.1||value.speed>4)throw new TypeError('Invalid recording view state');
          validateCamera(value.camera);ownedClock.pause();ownedClock.setSpeed(value.speed);speed.value=String(value.speed);ownedClock.seek(value.time);restoreCamera(ownedStage,value.camera);
        },dispose};
    }catch(error){dispose();throw error;}
  }});
  const ready=()=>{if(!controller)throw new Error('Replay is not ready');return controller;};
  return {host,get ready(){return host.ready;},get playback(){return ready();},get scene(){return scene;},get stage(){return stage;},get scenario(){return active.id;},
    /** Show another scenario; resolves true once its verified recording is on the stage. */
    selectScenario:async id=>{if(!await host.ready||!chooser)throw new Error('Replay is not ready');return chooser(id);},
    fit:()=>host.fit(),dispose:()=>host.dispose(),retry:()=>host.retry(),getViewState:()=>host.getViewState(),restoreViewState:value=>host.restoreViewState(value)};
}
