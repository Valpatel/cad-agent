/** Pure deep-link resolution. Variant identity is separate from a type label. */
export function selectScenario(entries,{scenario,componentType,variant}={}){
 const explicit=entries.find(entry=>entry.id===scenario);
 if(explicit)return{entry:explicit,explicit:true};
 if(componentType&&variant){const exact=entries.find(entry=>entry.componentVariants?.some(item=>item.type===componentType&&item.variant===variant));if(exact)return{entry:exact,variantMatched:true};}
 const type=entries.find(entry=>entry.componentTypes?.includes(componentType));
 if(type)return{entry:type,variantMatched:!variant,fallback:variant?'variant':null};
 return{entry:entries[0],fallback:componentType?'type':scenario?'scenario':null};
}

export function selectEquipment(components,{componentType,variant}={},resolveVariant=component=>component.variant){
 const typed=components.filter(component=>component.type===componentType);
 if(variant){const exact=typed.find(component=>resolveVariant(component)===variant);if(exact)return{component:exact,variantMatched:true};}
 return{component:typed[0],variantMatched:!variant,fallback:variant&&typed.length?'variant':componentType&&!typed.length?'type':null};
}
