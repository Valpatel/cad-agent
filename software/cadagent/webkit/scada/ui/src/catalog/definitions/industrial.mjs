/** Industrial extension metadata. Presentation contracts, never device physics. */
const freeze=value=>{if(value&&typeof value==='object'&&!Object.isFrozen(value)){Object.values(value).forEach(freeze);Object.freeze(value);}return value;};
const option=value=>({value,label:value==='none'?'No visible damage':value.split('-').map(word=>word[0].toUpperCase()+word.slice(1)).join(' ')});
export const DAMAGE_PROFILES=freeze({
 vessel:['none','leaking','ruptured','corroded'],
 machine:['none','jammed','worn','overheated'],
 pump:['none','cavitating','leaking','seized','overheated'],
 thermal:['none','overheated','refractory-damage','fuel-leak'],
 electricOven:['none','overheated','element-fault','door-seal-leak'],
 electrical:['none','short-circuit','overheated','burnt'],
 valve:['none','stuck','leaking','corroded'],
 pipe:['none','blocked','leaking','corroded'],
 sensor:['none','drift','broken','fouled'],
 control:['none','comms-loss','io-fault','power-loss'],
 membrane:['none','fouled','leaking','ruptured'],
 column:['none','leaking','fouled','overheated'],
 cyclone:['none','blocked','worn','leaking'],
 scrubber:['none','fouled','leaking','corroded'],
 cooling:['none','fouled','fan-fault','leaking'],
 chiller:['none','refrigerant-leak','compressor-fault','overheated'],
 electrolyzer:['none','membrane-damage','leaking','overheated'],
 fuelCell:['none','fuel-starved','stack-damage','overheated'],
 well:['none','leaking','blocked','corroded'],
 wind:['none','blade-damage','gearbox-fault','overheated'],
 aeration:['none','leaking','diffuser-fault','foaming'],
 steam:['none','bearing-fault','blade-damage','overheated'],
 fan:['none','blade-damage','seized','overheated']
});
export function damageField(profile){
 const values=DAMAGE_PROFILES[profile];if(!values)throw new RangeError(`Unknown damage profile: ${profile}`);
 return {key:'damage',label:'Illustrative damage',type:'select',default:'none',options:values.map(option)};
}
const numeric=(key,label,value,min=0,max=100,unit='%')=>({key,label,type:'number',default:value,min,max,step:1,unit});
const load=()=>numeric('load','Illustrative load',60);
const speed=()=>numeric('speed','Illustrative operating speed',60);
const level=()=>numeric('level','Illustrative fill',55);
const temperature=(value,min,max)=>numeric('temperature','Illustrative temperature',value,min,max,'°C');
const port=(id,label,medium,direction)=>({id,label,medium,direction});
const supply=()=>port('supply','Electrical supply','electricity','in');
const flowPorts=(medium='material')=>[port('inlet','Process inlet',medium,'in'),port('outlet','Process outlet',medium,'out'),supply()];
const extra=(id,label,medium,direction='out')=>port(id,label,medium,direction);
const thermalPorts=()=>[...flowPorts('material'),extra('fuel','Heating fuel','gas','in'),extra('air','Combustion or drying air','air','in'),extra('exhaust','Exhaust','gas')];
function type(type,label,category,drawingFamily,modelFamily,description,ports,fields,damageProfile){
 return {type,label,category,drawingFamily,modelFamily,description,ports,fields:[...fields,damageField(damageProfile)],damageProfile};
}
const production=(id,label,description,ports=flowPorts('solids'))=>type(id,label,'manufacturing','industrial','processor',description,ports,[load(),speed()],'machine');

export const SCADA_EXTENSION_DEFINITIONS=freeze([
 production('conveyor','Belt conveyor','Powered material belt with support rollers, travelling product and a distinct jam state.'),
 production('crusher','Jaw crusher','Feed hopper, crushing jaws and material discharge with wear and blockage detail.'),
 production('vibrating-screen','Vibrating screen','Multi-deck separation screen with visible feed, vibration and screened output.'),
 production('grinding-mill','Grinding mill','Rotating grinding chamber and a separate drive, with worn liner and overheating states.'),
 type('rotary-kiln','Rotary kiln','manufacturing','industrial','heater','Long heated rotating drum with burner, support tyres and refractory-damage detail.',thermalPorts(),[load(),speed(),temperature(500,0,1800)],'thermal'),
 type('oven','Conveyor oven','manufacturing','industrial','heater','Cutaway heating tunnel with upper and lower heating coils, a moving metal belt and traveling product trays.',thermalPorts(),[load(),temperature(180,-20,600)],'thermal'),
 type('rack-oven','Rack / batch oven','manufacturing','industrial','heater','Front-loading electric batch oven with stationary product shelves, a hinged inspection door, recirculating air and retained thermal glow.',[...flowPorts('material'),extra('air','Recirculating or make-up air','air','in'),extra('exhaust','Vent air','air')],[load(),numeric('temperature','Illustrative retained heat',45,0,100,'index'),{key:'open',label:'Door open',type:'boolean',default:false}],'electricOven'),
 type('dryer','Rotary dryer','manufacturing','industrial','heater','Heated tumbling drum with vapor discharge and drying-load illustration.',thermalPorts(),[load(),speed(),temperature(90,-20,400)],'thermal'),
 production('extruder','Screw extruder','Heated barrel and screw drive that advance feed into a formed product.',[port('inlet','Raw material','solids','in'),port('outlet','Extruded product','product','out'),supply(),extra('coolant-in','Cooling fluid supply','thermal-fluid','in'),extra('coolant-out','Cooling fluid return','thermal-fluid')]),
 production('tablet-press','Tablet press','Rotary turret, compression tooling and tablet discharge with an explicit jam state.'),
 production('filling-line','Filling line','Metered filling heads and a moving line of containers.',[port('inlet','Product liquid','liquid','in'),port('outlet','Filled containers','product','out'),supply()]),
 production('packaging-line','Packaging line','Product conveyor, wrapping station and sealed packages.',flowPorts('product')),
 production('granulator','Granulator','Granulating rotor and screened outlet for particle-size processing.'),
 production('forming-machine','Forming machine','Tooling station with a controlled forming stroke and product outfeed.',flowPorts('product')),
 production('drum-mixer','Drum mixer','Rotating mixing drum with inlet and discharge for bulk blending.'),
 production('paper-machine','Paper machine','Stock feed, forming belt and drying rollers leading to a paper reel.',[port('inlet','Stock slurry','slurry','in'),port('outlet','Paper product','product','out'),supply()]),
 type('weigh-hopper','Weigh hopper','manufacturing','industrial','storage','Weighing hopper, support load cells and a controlled solids discharge.',flowPorts('solids'),[level(),load()],'vessel'),
 production('screw-feeder','Screw feeder','Enclosed screw transport with a visible helix, intake and metered discharge.'),
 type('centrifuge','Industrial centrifuge','process','process','processor','Horizontal separation bowl, high-speed rotor and distinct liquid and solids outlets.',[...flowPorts('liquid'),extra('reject','Separated solids','solids')],[load(),speed()],'machine'),
 type('flotation-cell','Flotation cell','process','process','processor','Agitated separation cell with rising air bubbles and a mineral froth layer.',[...flowPorts('slurry'),extra('air','Flotation air','air','in'),extra('reject','Tailings','slurry')],[level(),load(),speed()],'machine'),
 type('membrane-filter','Membrane filter','process','process','processor','Parallel membrane channels with permeate, retained solids and visible membrane condition.',[...flowPorts('liquid'),extra('reject','Concentrate','liquid')],[load()],'membrane'),
 type('reverse-osmosis','Reverse osmosis skid','process','process','processor','Pressure membrane vessels, high-pressure pump and separate permeate and brine lines.',[...flowPorts('liquid'),extra('reject','Brine reject','liquid')],[load()],'membrane'),
 type('distillation-column','Distillation column','process','process','heater','Tall trayed column with reflux, reboiler heat and vapor separation.',[...flowPorts('liquid'),extra('vapor','Overhead vapor','gas'),extra('heat','Reboiler heat','thermal','in')],[level(),load(),temperature(120,0,600)],'column'),
 type('separator','Three-phase separator','process','process','processor','Horizontal settling vessel showing separate fluid layers and a gas outlet.',[...flowPorts('fluid'),extra('gas','Separated gas','gas'),extra('drain','Water drain','liquid')],[level(),load()],'vessel'),
 type('cyclone','Cyclone separator','process','process','processor','Tangential inlet, swirling separation chamber and conical solids discharge.',[...flowPorts('gas'),extra('solids','Separated solids','solids')],[load()],'cyclone'),
 type('scrubber','Wet scrubber','process','process','processor','Vertical gas-cleaning vessel with spray banks and a recirculating wash sump.',[...flowPorts('gas'),extra('wash','Wash liquid','liquid','in'),extra('drain','Wash drain','liquid')],[level(),load()],'scrubber'),
 type('cooling-tower','Cooling tower','process','process','heater','Induced-draft cooling tower with fan, falling water and exhaust plume.',[...flowPorts('thermal-fluid'),extra('air','Cooling air','air','in'),extra('vent','Warm air discharge','air')],[load(),speed(),temperature(32,-20,100)],'cooling'),
 type('chiller','Industrial chiller','process','process','heater','Compressor, evaporator and condenser loop with a cold-water outlet.',[...flowPorts('thermal-fluid'),extra('heat','Rejected heat','thermal')],[load(),temperature(7,-40,100)],'chiller'),
 type('evaporator','Falling-film evaporator','process','process','heater','Heated vessel with falling liquid film, vapor outlet and concentrated product.',[...flowPorts('liquid'),extra('vapor','Evaporated vapor','gas'),extra('heat','Heating duty','thermal','in')],[level(),load(),temperature(85,-20,400)],'column'),
 type('electrolyzer','Water electrolyzer','power','process','processor','Electrochemical plate stack converting a modeled water feed and electrical input into gas streams.',[port('inlet','Water feed','liquid','in'),port('outlet','Hydrogen outlet','gas','out'),supply(),extra('oxygen','Oxygen outlet','gas')],[load(),temperature(65,0,150)],'electrolyzer'),
 type('fuel-cell','Fuel-cell generator','power','process','generator','Fuel-cell plate stack, electrical output, heat recovery and water discharge.',[port('inlet','Fuel gas','gas','in'),port('output','Electrical output','electricity','out'),extra('water','Product water','liquid'),extra('heat','Rejected heat','thermal')],[load(),temperature(80,0,1000)],'fuelCell'),
 type('wellhead','Production wellhead','process','process','source','Christmas-tree wellhead with valves, a pressure readout and production outlet.',[port('outlet','Production fluid','fluid','out'),extra('gas','Production gas','gas'),extra('control','Well control','data','in')],[load(),{key:'open',label:'Production valve open',type:'boolean',default:true},numeric('value','Illustrative well pressure',350,0,100000,'kPa')],'well'),
 type('wind-turbine','Wind turbine','power','process','generator','Three-blade wind rotor, nacelle and tower with visible blade and gearbox conditions.',[port('output','Electrical output','electricity','out'),extra('control','Turbine control','data','in')],[load(),speed()],'wind'),
 type('aeration-basin','Aeration basin','process','process','processor','Open treatment basin with diffusers, rising bubbles and a visible liquid surface.',[...flowPorts('liquid'),extra('air','Diffuser air','air','in'),extra('sludge','Waste sludge','sludge')],[level(),load()],'aeration'),
 type('steam-turbine','Steam turbine','power','process','generator','Staged steam casing with a shaft-driven alternator and condensate outlet.',[port('inlet','Steam inlet','steam','in'),port('outlet','Steam exhaust','steam','out'),port('output','Electrical output','electricity','out')],[load(),speed(),temperature(450,0,650)],'steam'),
 type('fan','Axial ventilation fan','rotating','process','load','Guarded axial fan with a duct flange, rotating blades and visible mechanical damage.',[...flowPorts('air'),extra('control','Fan command','data','in')],[load(),speed()],'fan')
]);

/** Existing symbols retain their IDs and fields; damage is an added visual field. */
export const EXISTING_DAMAGE_PROFILES=freeze({
 digester:'vessel',tank:'vessel','gas-holder':'vessel','mixing-tank':'vessel',reactor:'vessel',clarifier:'vessel',silo:'vessel',
 'heat-exchanger':'column',filter:'membrane','gas-treatment':'scrubber',boiler:'thermal',flare:'thermal',
 pump:'pump','submersible-pump':'pump','dosing-pump':'pump',blower:'fan',compressor:'pump',motor:'machine',
 generator:'electrical',transformer:'electrical',breaker:'electrical',busbar:'electrical',battery:'electrical',ups:'electrical','solar-panel':'electrical','electrical-meter':'sensor',
 'gate-valve':'valve','control-valve':'valve','check-valve':'valve','relief-valve':'valve','butterfly-valve':'valve',
 'pressure-transmitter':'sensor','flow-meter':'sensor','temperature-sensor':'sensor','level-sensor':'sensor','gas-analyzer':'sensor',
 'plc-rack':'control','plc-cpu':'control','remote-io':'control',hmi:'control','scada-server':'control','network-switch':'control',radio:'control',pipe:'pipe',junction:'pipe'
});
