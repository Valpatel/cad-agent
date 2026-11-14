import {MAX_FILE_BYTES,validateModel,UNITS_MM} from './file-geometry.js';
export function fileURL(value,base=location.href){
  let url;try{url=new URL(value,base);}catch{throw new Error('Choose a valid model file URL.');}
  if(url.origin!==new URL(base).origin||!/^https?:$/.test(url.protocol)||url.username||url.password)throw new Error('Model files must be hosted on this site.');
  const extension=url.pathname.split('.').pop().toLowerCase();
  const format={stl:'stl',step:'step',stp:'step','3mf':'3mf'}[extension];
  if(!format)throw new Error('This viewer opens original STL, STEP and 3MF files.');
  url.hash='';return{url,format,name:decodeURIComponent(url.pathname.split('/').pop())};
}
/** Download and parse an original file. Cancellation terminates active CPU parsing. */
export async function loadFileGeometry(value,{signal,onProgress=()=>{},unit='millimeter',timeoutMs=30000,parseTimeoutMs=120000}={}){
  const source=fileURL(value),controller=new AbortController();
  const abort=()=>controller.abort(signal?.reason);signal?.addEventListener('abort',abort,{once:true});if(signal?.aborted)abort();
  let worker=null,timer,timedOut=false;
  const deadline=ms=>{clearTimeout(timer);timer=setTimeout(()=>{timedOut=true;controller.abort();},ms);};
  try{
    if(!UNITS_MM[unit])throw new Error('Choose a supported STL unit.');
    deadline(timeoutMs);onProgress('Downloading the original '+source.format.toUpperCase()+' file…');
    const response=await fetch(source.url,{signal:controller.signal,cache:'no-store',redirect:'error'});
    if(!response.ok)throw new Error(`The model download returned HTTP ${response.status}.`);
    const declared=Number(response.headers.get('content-length'));
    if(declared>MAX_FILE_BYTES)throw new Error('This original exceeds the 128 MB browser preview limit.');
    const reader=response.body?.getReader(),chunks=[];let received=0,buffer;
    if(reader){
      for(;;){const {done,value}=await reader.read();if(done)break;received+=value.length;if(received>MAX_FILE_BYTES){await reader.cancel();throw new Error('This original exceeds the 128 MB browser preview limit.');}chunks.push(value);}
      const bytes=new Uint8Array(received);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}buffer=bytes.buffer;
    }else buffer=await response.arrayBuffer();
    if(!buffer.byteLength||buffer.byteLength>MAX_FILE_BYTES)throw new Error('The downloaded model is empty or too large to preview.');
    const sourceBytes=buffer.byteLength;
    if(controller.signal.aborted)throw new DOMException('Cancelled','AbortError');
    onProgress('Preparing the '+source.format.toUpperCase()+' reader…');deadline(parseTimeoutMs);
    const workerURL=new URL(source.format==='step'?'./file-step-worker.js':'./file-mesh-worker.js',import.meta.url);workerURL.search=new URL(import.meta.url).search;
    worker=new Worker(workerURL,source.format==='step'?undefined:{type:'module'});
    const result=await new Promise((resolve,reject)=>{
      const stop=()=>reject(new DOMException('Cancelled','AbortError'));
      controller.signal.addEventListener('abort',stop,{once:true});
      const finish=(fn,value)=>{controller.signal.removeEventListener('abort',stop);fn(value);};
      worker.onmessage=({data})=>{if(data.phase)onProgress(data.phase);else if(data.error)finish(reject,new Error(data.error));else if(data.model)finish(resolve,data.model);};
      worker.onerror=()=>finish(reject,new Error('The model reader could not start or stopped unexpectedly. Please retry.'));
      worker.postMessage({buffer,format:source.format,name:source.name,unit},[buffer]);
      if(controller.signal.aborted)stop();
    });
    return{...validateModel(result),sourceURL:source.url.href,sourceName:source.name,sourceBytes};
  }catch(error){
    if(timedOut)throw new Error('The model download or reader timed out. Retry, or download the original for a desktop CAD tool.');
    if(controller.signal.aborted)throw new DOMException('Cancelled','AbortError');
    throw error;
  }finally{clearTimeout(timer);controller.abort();signal?.removeEventListener('abort',abort);worker?.terminate();}
}
