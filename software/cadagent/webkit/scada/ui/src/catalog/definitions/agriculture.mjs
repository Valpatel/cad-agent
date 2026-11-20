/** DRAFT contracts. Original presentation metadata; no model, clock or IO. */
const n=(key,label,value=50)=>({key,label,type:'number',default:value,min:0,max:100,step:1,unit:'index'});
const percent=(key,label,value=50)=>({...n(key,label,value),unit:'%'});
const select=(key,label,values,value=values[0])=>({key,label,type:'select',default:value,options:values.map(value=>({value,label:value.replaceAll('-',' ')}))});
const p=(id,label,medium,direction)=>({id,label,medium,direction});
const water=()=>[p('inlet','Liquid feed','liquid','in'),p('outlet','Liquid return','liquid','out')];
const power=()=>p('supply','Electrical supply','electricity','in');
const control=()=>p('control','Operating command','data','in');
const measure=()=>p('measurement','Measured process','measurement','out');
const light=()=>p('light','Incident light','optical','in');
const air=()=>p('air','Aeration supply','air','in');
const sensor=()=>[p('measurement','Observed variable','measurement','in'),p('signal','Measurement signal','data','out'),power()];
const level=()=>percent('level','Illustrative water inventory',55);
const load=()=>percent('load','Illustrative operating level',60);
const oxygen=()=>n('oxygen','Dissolved oxygen illustration',60);
const moisture=()=>n('moisture','Root-zone moisture illustration',55);
const phase=()=>select('phase','Irrigation phase',['idle','filling','holding','draining'],'holding');
const damage=values=>select('damage','Illustrative damage',['none',...values]);
const connected=()=>({key:'connected',label:'Connected',type:'boolean',default:true});
const entry=(type,label,category,modelFamily,description,ports,fields,damages)=>({type,label,category,drawingFamily:'agriculture',modelFamily,description,ports,fields:[...fields,damage(damages)],provenance:'Original SVG geometry informed by structural references in docs/agriculture-references.md. No vendor imagery or calibrated operating values.'});
export const SCADA_AGRICULTURE_DEFINITIONS=[
 entry('fish-tank','Aquaculture fish tank','agriculture','storage','Aquatic vessel with visible inventory, independent aeration and decorative fish silhouettes.',[...water(),air(),p('drain','Solids drain','liquid','out'),measure()],[level(),oxygen(),load()],['leaking','cracked','blocked']),
 entry('biofilter','Biological media filter','agriculture','processor','Visible biomedia vessel with separately supplied water and air.',[...water(),air(),p('waste','Retained solids purge','sludge','out'),measure()],[level(),oxygen(),load()],['fouled','blocked','leaking']),
 entry('media-grow-bed','Media grow bed','agriculture','storage','Granular root bed with an externally supplied flood/drain phase.',[...water(),light(),measure()],[level(),moisture(),phase()],['blocked','leaking','fouled']),
 entry('dwc-raft-bed','Deep-water raft bed','agriculture','storage','Floating plant raft above a separate water and aeration volume.',[...water(),air(),light(),measure()],[level(),oxygen(),load()],['blocked','leaking','air-loss']),
 entry('nft-channel','Nutrient-film channel','agriculture','processor','Shallow solution channel with exposed root positions and gravity return.',[...water(),light(),measure()],[moisture(),load()],['blocked','leaking','fouled']),
 entry('ebb-flow-table','Ebb-and-flow nursery table','agriculture','storage','Raised nursery tray with fill, hold and drain phases controlled by the host.',[...water(),light(),control(),measure()],[level(),moisture(),phase()],['blocked','leaking','timer-stall']),
 entry('drip-zone','Drip irrigation zone','agriculture','processor','Emitter manifold above substrate pots with a separately visible collection drain.',[...water(),light(),measure()],[moisture(),load()],['blocked','leaking','uneven-feed']),
 entry('aeroponic-chamber','Aeroponic root chamber','agriculture','storage','Enclosed roots supplied by an explicit mist manifold and drain.',[...water(),light(),control(),measure()],[moisture(),load()],['blocked','leaking','nozzle-fault']),
 entry('grow-light','Horticultural light panel','agriculture','load','Downward-facing light array with electrical input, emitted light and rejected heat.',[power(),p('light','Emitted light','optical','out'),p('heat','Rejected heat','thermal','out'),control()],[n('light','Illustrative light output',60),load()],['overheated','driver-fault','burnt']),
 entry('greenhouse-vent','Greenhouse vent','climate','valve','Hinged roof vent with explicit position and an independent air path.',[p('inlet','Outside air','air','in'),p('outlet','Zone air','air','out'),power(),control()],[percent('opening','Vent opening',50),n('airflow','Illustrative air exchange',50)],['stuck','panel-damage','actuator-fault']),
 entry('shade-screen','Retractable shade screen','climate','valve','Retracting mesh screen with visible deployment and separate incident/transmitted light.',[p('light-in','Incident light','optical','in'),p('light-out','Transmitted light','optical','out'),power(),control()],[percent('opening','Screen retraction',50),n('light','Transmitted light illustration',50)],['stuck','torn','actuator-fault']),
 entry('evaporative-pad','Evaporative cooling pad','climate','processor','Wetted pad with distinct air passage and recirculating water connections.',[p('inlet','Water feed','liquid','in'),p('drain','Water return','liquid','out'),p('air-in','Incoming air','air','in'),p('air-out','Conditioned air','air','out'),measure()],[n('moisture','Pad wetness illustration',60),n('airflow','Illustrative airflow',60),n('humidity','Outlet humidity illustration',55)],['dry-pad','fouled','leaking']),
 entry('dehumidifier','Air dehumidifier','climate','processor','Air coil enclosure with fan, condensate collector and separate drain.',[p('air-in','Humid air','air','in'),p('air-out','Conditioned air','air','out'),p('drain','Condensate drain','liquid','out'),power(),control()],[n('humidity','Inlet humidity illustration',60),level(),load()],['blocked-drain','iced-coil','compressor-fault']),
 entry('water-quality-probe','Water-quality probe','instruments','sensor','Immersed probe with explicit pH, EC or dissolved-oxygen identity; readings remain illustrative indices.',sensor(),[connected(),select('measurement','Measurement identity',['ph','ec','do'],'do'),n('value','Illustrative sensor reading',60)],['drift','fouled','disconnected']),
 entry('humidity-sensor','Humidity sensor','instruments','sensor','Ventilated sensing enclosure with a humidity identity and external reading.',sensor(),[connected(),n('humidity','Illustrative humidity reading',55)],['drift','condensation','disconnected']),
 entry('light-sensor','PAR light sensor','instruments','sensor','Quantum-sensor silhouette with a light identity; no conversion to physical PAR is inferred.',sensor(),[connected(),n('light','Illustrative light reading',60)],['drift','occluded','disconnected']),
 entry('air-diffuser','Submerged air diffuser','agriculture','processor','Porous diffuser and restrained bubble plume driven by supplied air.',[p('inlet','Air delivery','air','in'),p('bubbles','Dispersed air','air','out')],[n('airflow','Illustrative air delivery',60),oxygen()],['fouled','blocked','disconnected']),
];
const taxonomy={
 'fish-tank':[['agriculture','aquaculture'],['aquaponics','recirculating-aquaculture'],['aquaculture'],['storage','circulation']],
 biofilter:[['agriculture','aquaculture','water-treatment'],['aquaponics','recirculating-aquaculture'],['biological-filtration'],['treatment','aeration']],
 'media-grow-bed':[['agriculture'],['aquaponics','hydroponics'],['media-bed','flood-and-drain'],['growing','storage']],
 'dwc-raft-bed':[['agriculture'],['aquaponics','hydroponics'],['dwc','raft'],['growing','aeration']],
 'nft-channel':[['agriculture'],['aquaponics','hydroponics'],['nft','nutrient-film-technique'],['growing','transfer']],
 'ebb-flow-table':[['agriculture'],['hydroponics','nursery'],['ebb-and-flow','flood-and-drain'],['growing','irrigation']],
 'drip-zone':[['agriculture'],['hydroponics','greenhouse'],['drip','substrate'],['growing','irrigation']],
 'aeroponic-chamber':[['agriculture'],['hydroponics','vertical-farm'],['aeroponic','misting'],['growing','irrigation']],
 'grow-light':[['agriculture'],['greenhouse','vertical-farm','indoor-growing'],['led','supplemental-light','sole-source-light'],['illumination']],
 'greenhouse-vent':[['agriculture'],['greenhouse','climate-control'],['natural-ventilation'],['air-exchange']],
 'shade-screen':[['agriculture'],['greenhouse','climate-control'],['retractable-shade'],['light-control']],
 'evaporative-pad':[['agriculture','building-services'],['greenhouse','climate-control'],['fan-and-pad','evaporative-cooling'],['cooling','humidification']],
 dehumidifier:[['agriculture','building-services'],['greenhouse','indoor-growing','climate-control'],['condensing-dehumidification'],['dehumidification']],
 'water-quality-probe':[['agriculture','aquaculture','water-treatment'],['aquaponics','hydroponics','water-monitoring'],['ph','ec','dissolved-oxygen'],['measurement']],
 'humidity-sensor':[['agriculture','building-services'],['greenhouse','climate-control'],['humidity-monitoring'],['measurement']],
 'light-sensor':[['agriculture'],['greenhouse','indoor-growing'],['par','quantum-sensing'],['measurement']],
 'air-diffuser':[['agriculture','aquaculture','water-treatment'],['aquaponics','recirculating-aquaculture','water-aeration'],['diffused-aeration'],['aeration']],
};
for(const item of SCADA_AGRICULTURE_DEFINITIONS){const [industries,systems,technologies,functions]=taxonomy[item.type];item.taxonomy={industries,systems,technologies,functions};}
export const AGRICULTURE_TYPES=SCADA_AGRICULTURE_DEFINITIONS.map(item=>item.type);
export function getAgricultureDefinition(type){const item=SCADA_AGRICULTURE_DEFINITIONS.find(item=>item.type===type);if(!item)throw new RangeError(`Unknown agriculture type: ${type}`);return item;}
