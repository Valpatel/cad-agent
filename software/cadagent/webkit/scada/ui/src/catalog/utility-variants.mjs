/** Explicit illustrative carrier choices for reusable utilities.
 * These are adapter contracts, never pump metallurgy or service certifications.
 * Model authors still assign the exact fluid identity to each local circuit.
 */

const FLUIDS = Object.freeze({
  water: {medium:'liquid', label:'Water service', fluid:'water',
    supportedFluids:['water','primary-water','secondary-water','reactor-water','cooling-water','pool-water','geothermal-water','collection-water']},
  'thermal-fluid': {medium:'thermal-fluid', label:'Heat-transfer fluid', fluid:'thermal-fluid', supportedFluids:['thermal-fluid','thermal-oil']},
  helium: {medium:'gas', label:'Helium circulation', fluid:'helium', supportedFluids:['helium']},
  sodium: {medium:'thermal-fluid', label:'Sodium loop concept', fluid:'sodium', supportedFluids:['sodium']},
  salt: {medium:'thermal-fluid', label:'Salt loop concept', fluid:'salt', supportedFluids:['salt']},
  'heavy-water': {medium:'liquid', label:'Heavy-water loop concept', fluid:'heavy-water', supportedFluids:['heavy-water']},
  'organic-working-fluid': {medium:'thermal-fluid', label:'Organic working-fluid loop', fluid:'organic-working-fluid', supportedFluids:['organic-working-fluid']},
  'liquid-fuel': {medium:'liquid', label:'Liquid-fuel transfer', fluid:'liquid-fuel', supportedFluids:['liquid-fuel','diesel','gasoline']},
});

function utilityVariants(ports) {
  return Object.entries(FLUIDS).map(([id,fluid]) => ({
    id, label:fluid.label, supportedFluids:fluid.supportedFluids,
    portOverrides:Object.fromEntries(ports.map(port => [port,{medium:fluid.medium}])),
    circuitOverrides:{process:{fluid:fluid.fluid,supportedFluids:fluid.supportedFluids}},
    description:'Explicit illustrative compatibility selection; engineering service suitability is not established.',
  }));
}

function exchangerVariant(id,label,hot,cold) {
  const hotFluid=FLUIDS[hot],coldFluid=FLUIDS[cold];
  return {
    id,label,
    portOverrides:{
      'hot-in':{medium:hotFluid.medium},'hot-out':{medium:hotFluid.medium},
      'cold-in':{medium:coldFluid.medium},'cold-out':{medium:coldFluid.medium},
    },
    circuitOverrides:{
      hot:{fluid:hotFluid.fluid,supportedFluids:hotFluid.supportedFluids},
      cold:{fluid:coldFluid.fluid,supportedFluids:coldFluid.supportedFluids},
    },
  };
}

export function addUtilityVariants(descriptor) {
  if (descriptor.type === 'busbar') return {
    ...descriptor,
    variants: [{
      id: 'bidirectional',
      label: 'Bidirectional AC common bus',
      description: 'A common AC conductor with four bidirectional connections for explicit supply, load and storage branches. The external model determines each branch flow.',
      portOverrides: Object.fromEntries(descriptor.ports.map(port => [port.id, {direction:'bidirectional'}])),
      powerDomains: Object.fromEntries(descriptor.ports.map(port => [port.id, 'ac'])),
    }],
  };
  const flowTypes=['pump','submersible-pump','pipe','gate-valve','control-valve','check-valve','butterfly-valve','relief-valve'];
  if(flowTypes.includes(descriptor.type)) {
    const ports=descriptor.ports.filter(port=>['liquid','fluid'].includes(port.medium)).map(port=>port.id);
    return {
      ...descriptor,
      circuits:[{id:'process',ports,fluid:'water',supportedFluids:FLUIDS.water.supportedFluids}],
      variants:utilityVariants(ports),
      // Preserve unspecified legacy media (notably generic relief-valve ports).
      // An authored v2 graph must select a carrier variant explicitly.
      defaultVariant:null,
    };
  }
  if(descriptor.type==='blower')return {
    ...descriptor,
    circuits:[{id:'process',ports:['intake','discharge'],fluid:'air'}],
    variants:[{
      id:'helium',label:'Helium circulator concept',supportedFluids:['helium'],
      portOverrides:{intake:{medium:'gas',label:'Helium inlet'},discharge:{medium:'gas',label:'Helium outlet'}},
      circuitOverrides:{process:{fluid:'helium',supportedFluids:['helium']}},
    }],
  };
  if(descriptor.type==='heat-exchanger')return {
    ...descriptor,
    circuits:[
      {id:'hot',ports:['hot-in','hot-out'],fluid:'thermal-fluid'},
      {id:'cold',ports:['cold-in','cold-out'],fluid:'thermal-fluid'},
    ],
    variants:[
      exchangerVariant('water-water','Water / water','water','water'),
      exchangerVariant('heavy-water-water','Heavy water / cooling water','heavy-water','water'),
      exchangerVariant('helium-water','Helium / water','helium','water'),
      exchangerVariant('sodium-sodium','Isolated sodium loops','sodium','sodium'),
      exchangerVariant('salt-salt','Isolated salt loops','salt','salt'),
      exchangerVariant('salt-water','Salt / water','salt','water'),
      exchangerVariant('thermal-fluid-water','Thermal fluid / water','thermal-fluid','water'),
      {...exchangerVariant('geothermal-working-fluid','Geothermal water / organic working fluid','water','organic-working-fluid'),
        circuitOverrides:{hot:{fluid:'geothermal-water',supportedFluids:['geothermal-water']},cold:{fluid:'organic-working-fluid',supportedFluids:['organic-working-fluid']}}},
    ],
  };
  if(descriptor.type==='separator')return {
    ...descriptor,
    variants:[{
      id:'flash-water',label:'Water / steam flash separator',
      portOverrides:{inlet:{medium:'liquid'},outlet:{medium:'liquid'},gas:{medium:'steam',label:'Separated steam'}},
      circuits:[{id:'process',ports:['inlet','outlet','gas','drain'],fluid:'geothermal-water',phaseChange:true}],
    }],
  };
  if(descriptor.type==='wellhead')return {
    ...descriptor,
    variants:[{
      id:'steam-well',label:'Dry-steam production well',
      portOverrides:{outlet:{medium:'steam',label:'Produced steam'}},disabledPorts:['gas'],
      circuits:[{id:'process',ports:['outlet'],fluid:'geothermal-water',phaseChange:true}],
    },{
      id:'geothermal-water',label:'Geothermal liquid production well',
      portOverrides:{outlet:{medium:'liquid',label:'Produced geothermal water'}},disabledPorts:['gas'],
      circuits:[{id:'process',ports:['outlet'],fluid:'geothermal-water'}],
    }],
  };
  return descriptor;
}
