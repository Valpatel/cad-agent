/** Host adapter; the reusable UI package never imports this model package. */
export function createPlaceholderAdapter(model,{readOnly=false}={}){
  if(!model||typeof model.getSnapshot!=='function'||typeof model.subscribe!=='function'||typeof model.dispatch!=='function')throw new TypeError('A placeholder model instance is required.');
  if(typeof readOnly!=='boolean')throw new TypeError('readOnly must be boolean.');
  return Object.freeze({getSnapshot:()=>model.getSnapshot(),subscribe:listener=>model.subscribe(listener),...(readOnly?{}:{dispatch:command=>model.dispatch(command)})});
}
