/** A page of named recordings from a replay index: `<div id="replay" data-replay-index="index.json">`.
 * `?scenario=<id>` opens that scenario. The index's hashes verify the meshes and each recording before display. */
import {createReplayViewer} from './viewer.js';
import {loadReplayIndex} from './replay.js';

const lifetime=new AbortController(),status=document.querySelector('#receipt-status'),container=document.querySelector('#replay');
let viewer;
async function start(){
  status.textContent='Checking the recording index…';document.body.dataset.ready='loading';
  const placeholder=document.createElement('p');placeholder.className='replay-load-message';placeholder.textContent='Loading recorded simulation…';container.replaceChildren(placeholder);
  try{
    const index=await loadReplayIndex(new URL(container.dataset.replayIndex,location.href),{signal:lifetime.signal});
    const wanted=new URLSearchParams(location.search).get('scenario');
    placeholder.remove();
    viewer=createReplayViewer(container,{title:index.title,scenarios:index.scenarios,meshesUrl:index.meshes?.url,meshesHash:index.meshes?.expectedHash,
      initialScenario:index.scenarios.some(s=>s.id===wanted)?wanted:undefined,signal:lifetime.signal});
    window.__replay=viewer;
    const ready=()=>{status.textContent=`${index.scenarios.length} recorded scenarios · shapes and every recording verified by SHA-256 before display`;document.body.dataset.ready='1';};
    viewer.host.subscribe(event=>{if(event.type==='status'&&event.state==='ready')ready();});
    if(!await viewer.ready)throw new Error('Recording could not be loaded; use Retry viewer to retry.');
    ready();
  }catch(error){
    if(lifetime.signal.aborted)return;status.textContent=`Could not open recorded simulation: ${error.message}`;document.body.dataset.ready='error';
    if(!viewer){placeholder.textContent='The recording index could not load.';const retry=document.createElement('button');retry.className='replay-retry';retry.type='button';retry.textContent='Retry recording';retry.addEventListener('click',start,{once:true,signal:lifetime.signal});placeholder.append(document.createElement('br'),retry);}
  }
}
// A BFCache entry keeps this document and WebGL owner alive; visibilitychange already pauses playback.
window.addEventListener('pagehide',event=>{if(!event.persisted){lifetime.abort();viewer?.dispose();}});
start();
