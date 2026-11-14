/** Recorded simulation adapter: shared host, stage, camera gestures and theme; no physics backend. */
import {createViewerHost} from '../host/viewer-host.js';
import {bindStageControls,captureCamera,restoreCamera,validateCamera} from '../host/stage-controls.js';
import {createStage} from '../model/stage.js';
import {createPlayback,loadRecording,validateRecording} from './replay.js';
import {createPoseScene} from './scene.js';

const el=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};

/** Mount into a connected, sized container. Supply data or a same-origin recording URL. */
export function createReplayViewer(container,{recording,recordingUrl,expectedHash,title='Recorded simulation replay',signal}={}) {
  let controller,scene,stage;
  const host=createViewerHost(container,{title,signal,async mount({viewport,inspector,signal,onProgress,onState}){
    onProgress('Checking recorded poses…');
    const data=recording?validateRecording(recording):await loadRecording(recordingUrl,{signal,expectedHash});
    signal.throwIfAborted();
    const root=viewport.closest('.cad-viewer-host'),controls=el('div');controls.className='replay-controls';
    root.classList.add('cad-replay-host');root.insertBefore(controls,viewport.parentElement);
    const events=new AbortController(),system=matchMedia('(prefers-color-scheme: dark)');
    let unbind,offFrame,ownedScene,ownedStage,ownedClock,disposed=false;
    const dispose=()=>{
      if(disposed)return;disposed=true;events.abort();system.removeEventListener('change',palette);signal.removeEventListener('abort',dispose);
      offFrame?.();unbind?.();ownedClock?.dispose();ownedScene?.dispose();ownedStage?.dispose();controls.remove();
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
      ownedScene=createPoseScene(ownedStage,data);scene=ownedScene;ownedStage.frame(ownedScene.height);
      const play=el('button','Play'),restart=el('button','Restart'),timeLabel=el('label','Time'),time=el('input'),speedLabel=el('label','Speed'),speed=el('select'),readout=el('output');
      play.type=restart.type='button';play.setAttribute('aria-label','Play recording');restart.setAttribute('aria-label','Restart recording');
      time.type='range';time.min='0';time.max=String(data.duration);time.step='.001';time.value='0';time.setAttribute('aria-label','Recording time');
      timeLabel.className='replay-time';timeLabel.append(time);
      speed.setAttribute('aria-label','Playback speed');for(const n of [.25,.5,1,2]){const option=el('option',`${n}×`);option.value=n;option.selected=n===1;speed.append(option);}speedLabel.append(speed);
      readout.className='replay-readout';readout.setAttribute('aria-label','Recorded time');
      controls.append(play,restart,timeLabel,readout,speedLabel);
      ownedClock=createPlayback(data,(state,poses)=>{
        ownedScene.apply(poses);time.value=String(state.time);time.setAttribute('aria-valuetext',`${state.time.toFixed(2)} of ${state.duration.toFixed(2)} seconds`);
        readout.textContent=`${state.time.toFixed(2)} / ${state.duration.toFixed(2)} s`;
        play.textContent=state.playing?'Pause':'Play';play.setAttribute('aria-label',state.playing?'Pause recording':'Play recording');play.setAttribute('aria-pressed',String(state.playing));
        let custom=speed.querySelector('[data-custom-speed]');
        if(![.25,.5,1,2].includes(state.speed)){if(!custom){custom=el('option');custom.dataset.customSpeed='true';speed.append(custom);}custom.value=String(state.speed);custom.textContent=`${state.speed}×`;}
        else custom?.remove();
        speed.value=String(state.speed);
        onState({state:'ready',playback:state});
      });controller=ownedClock;
      const listen=(node,type,fn)=>node.addEventListener(type,fn,{signal:events.signal});
      listen(play,'click',()=>ownedClock.state().playing?ownedClock.pause():ownedClock.play());
      listen(restart,'click',()=>{ownedClock.pause();ownedClock.seek(0);});
      listen(time,'input',()=>{const requested=+time.value;ownedClock.pause();ownedClock.seek(requested);});
      listen(speed,'change',()=>ownedClock.setSpeed(+speed.value));
      listen(document,'visibilitychange',()=>{if(document.hidden)ownedClock.pause();});
      listen(document,'cad-themechange',palette);system.addEventListener('change',palette);palette();
      const heading=el('h3','Recorded evidence'),description=el('p',`${data.bodies.length} bodies · ${data.frames.length} captured frames · ${data.duration.toFixed(2)} seconds.`);
      const limits=el('p','Playback interpolates a completed solver run. Changing speed or time does not change forces or recompute dynamics.');
      const list=el('ul');for(const body of data.bodies)list.append(el('li',body.label));inspector.append(heading,description,list,limits);
      const selection=root.querySelector('.cad-viewer-selection');selection.textContent='Drag to orbit · two fingers to pan/zoom · Home to fit';selection.removeAttribute('aria-live');
      unbind=bindStageControls(viewport,ownedStage,()=>ownedScene.fit());
      offFrame=ownedStage.onFrame((_,dt)=>ownedClock.advance(dt));ownedScene.fit();ownedStage.start();
      const documentId=crypto.randomUUID();
      return {fit:()=>ownedScene.fit(),
        getViewState:()=>({version:1,kind:'recorded-simulation',documentId,camera:captureCamera(ownedStage),time:ownedClock.state().time,speed:ownedClock.state().speed}),
        restoreViewState(value){
          if(!value||value.version!==1||value.kind!=='recorded-simulation'||value.documentId!==documentId||!Number.isFinite(value.time)||value.time<0||value.time>data.duration||!Number.isFinite(value.speed)||value.speed<.1||value.speed>4)throw new TypeError('Invalid recording view state');
          validateCamera(value.camera);ownedClock.pause();ownedClock.setSpeed(value.speed);speed.value=String(value.speed);ownedClock.seek(value.time);restoreCamera(ownedStage,value.camera);
        },dispose};
    }catch(error){dispose();throw error;}
  }});
  const ready=()=>{if(!controller)throw new Error('Replay is not ready');return controller;};
  return {host,get ready(){return host.ready;},get playback(){return ready();},get scene(){return scene;},get stage(){return stage;},
    fit:()=>host.fit(),dispose:()=>host.dispose(),retry:()=>host.retry(),getViewState:()=>host.getViewState(),restoreViewState:value=>host.restoreViewState(value)};
}
