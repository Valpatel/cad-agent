// Build-time neutral equipment icons. No host, simulation, clock or image code.
import {renderScadaComponent} from '../../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';
const NS='http://www.w3.org/2000/svg';
const inherited=new Set(['fill','fill-opacity','fill-rule','stroke','stroke-width','stroke-opacity','stroke-dasharray','stroke-dashoffset','stroke-linecap','stroke-linejoin','visibility','font-family','font-size','font-weight','text-anchor','dominant-baseline','paint-order']);
const defaults={opacity:'1',display:'inline',filter:'none','clip-path':'none',mask:'none',transform:'none','transform-origin':'0px 0px','transform-box':'view-box'};
const properties=['fill','fill-opacity','fill-rule','stroke','stroke-width','stroke-opacity','stroke-dasharray','stroke-dashoffset','stroke-linecap','stroke-linejoin','opacity','display','visibility','filter','clip-path','mask','transform','transform-origin','transform-box','font-family','font-size','font-weight','text-anchor','dominant-baseline','paint-order'];
export function exportSymbol(type,variant,id,{compact=true}={}){
  const holder=document.createElement('div');
  holder.style.cssText='width:180px;height:136px;position:relative';
  holder.innerHTML=renderScadaComponent(type,{...(variant?{variant}:{}),id,state:{active:true,running:false,status:'normal',fault:false,damage:'none'}});
  document.body.append(holder);
  const output=document.createElementNS(NS,'svg');
  output.setAttribute('viewBox','0 0 180 136');
  output.setAttribute('width','180');output.setAttribute('height','136');
  for(const original of holder.querySelectorAll('.scada-component>svg,.scada-component>.twin-equipment-art>svg')){
    const clone=original.cloneNode(true);
    const originals=[original,...original.querySelectorAll('*')];
    const copies=[clone,...clone.querySelectorAll('*')];
    originals.forEach((element,index)=>{
      const computed=getComputedStyle(element);const copy=copies[index];const parent=index?getComputedStyle(element.parentElement):null;
      copy.removeAttribute('class');copy.removeAttribute('style');
      for(const prop of properties){
        let value=computed.getPropertyValue(prop);
        if(prop==='font-family')value='Arial, sans-serif';
        value=value.replace(/url\(["']?[^)"']*#([^)'"\s]+)["']?\)/g,'url(#$1)');
        const parentValue=parent?.getPropertyValue(prop);
        const redundant=compact&&parent&&!element.hasAttribute(prop)&&(inherited.has(prop)?(prop==='font-family'||value===parentValue):value===defaults[prop]);
        if(value&&!redundant)copy.style.setProperty(prop,value);
      }
      copy.style.removeProperty('animation');
    });
    clone.setAttribute('x','0');clone.setAttribute('y','0');clone.setAttribute('width','180');clone.setAttribute('height','136');
    output.append(clone);
  }
  holder.remove();
  if(!output.children.length)throw Error('No artwork for '+type);
  return new XMLSerializer().serializeToString(output);
}
