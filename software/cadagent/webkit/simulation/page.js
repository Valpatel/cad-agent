import {createReplayViewer} from './viewer.js';
import {loadReceipt} from './replay.js';

const lifetime=new AbortController(),status=document.querySelector('#receipt-status'),container=document.querySelector('#replay');
let viewer;
async function start(){
  status.textContent='Checking the recording receipt…';document.body.dataset.ready='loading';
  const placeholder=document.createElement('p');placeholder.className='replay-load-message';placeholder.textContent='Loading recorded simulation…';container.replaceChildren(placeholder);
  try{
    const receipt=await loadReceipt(new URL('./examples/two-link-arm/receipt.json',import.meta.url),{signal:lifetime.signal});
    placeholder.remove();viewer=createReplayViewer(container,{title:'Recorded robot simulation',recordingUrl:new URL('./examples/two-link-arm/recording.json',import.meta.url),expectedHash:receipt.artifacts['recording.json'],signal:lifetime.signal});
    window.__replay=viewer;
    const ready=()=>{
      status.textContent=`MuJoCo ${receipt.engine.version} · ${receipt.effective_settings.frame_count} captured frames · exact recording hash verified`;
      document.querySelector('#solver-summary').textContent=`Recorded ${receipt.effective_settings.duration_s} s using ${receipt.effective_settings.completed_steps} solver steps of ${receipt.effective_settings.timestep_s} s; samples at ${receipt.effective_settings.sample_hz} Hz. Playback is interpolation of this completed run.`;
      document.body.dataset.ready='1';
    };
    viewer.host.subscribe(event=>{if(event.type==='status'&&event.state==='ready')ready();});
    if(!await viewer.ready)throw new Error('Recording could not be loaded; use Retry viewer to retry.');
    ready();
  }catch(error){
    if(lifetime.signal.aborted)return;status.textContent=`Could not open recorded simulation: ${error.message}`;document.body.dataset.ready='error';
    if(!viewer){placeholder.textContent='The recording receipt could not load.';const retry=document.createElement('button');retry.className='replay-retry';retry.type='button';retry.textContent='Retry recording';retry.addEventListener('click',start,{once:true,signal:lifetime.signal});placeholder.append(document.createElement('br'),retry);}
  }
}
// A BFCache entry keeps this document and WebGL owner alive; visibilitychange already pauses playback.
window.addEventListener('pagehide',event=>{if(!event.persisted){lifetime.abort();viewer?.dispose();}});
start();
