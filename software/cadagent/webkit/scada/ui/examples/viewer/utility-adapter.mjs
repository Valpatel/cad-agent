/** Translate a host model to the viewer contract. No DOM or viewer imports. */
export function createUtilityAdapter(model, {readOnly = false} = {}) {
  const getSnapshot = () => {
    const state = model.getSnapshot(), powered = !state.generatorFault;
    const flowing = state.pumpOn && state.valveOpen && powered;
    const common = {running:state.running, fault:false, status:'normal'};
    const flow = flowing ? 20 + state.demandPct / 2 : 0;
    return {
      minutes:state.minutes, running:state.running,
      controls:{pumpOn:state.pumpOn, valveOpen:state.valveOpen, demandPct:state.demandPct},
      components:{
        tank:{...common, active:true, level:state.tankLevel},
        pump:{...common, active:state.pumpOn && powered, status:powered ? 'normal' : 'offline'},
        valve:{...common, active:flowing, open:state.valveOpen},
        meter:{...common, active:flowing, value:flow},
        generator:{...common, active:powered, fault:state.generatorFault, load:state.pumpOn && powered ? state.demandPct : 0},
      },
      flows:{waterIntake:flowing, pumpedWater:flowing, deliveredWater:flowing, pumpPower:state.pumpOn && powered},
    };
  };
  return {
    getSnapshot,
    subscribe:listener => model.subscribe(() => listener(getSnapshot())),
    ...(readOnly ? {} : {dispatch:command => model.dispatch(command)}),
  };
}
