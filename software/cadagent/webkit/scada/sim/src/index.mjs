/** Headless placeholder models. Importing this entry starts no IO or clocks. */
export {PlaceholderSystemModel} from './placeholder-system.mjs';
export {createPlaceholderAdapter} from './adapter.mjs';
export {MODEL_DESCRIPTORS,MODEL_FAMILIES,getModelDescriptor,createModelDefinition} from './model-registry.mjs';
export {validatePlaceholderModelDefinition,PLACEHOLDER_MODEL_FORMAT,PLACEHOLDER_MODEL_VERSION} from './validation.mjs';
export {ComponentModel,SourceModel,StorageModel,PumpModel,ValveModel,PipeModel,ProcessorModel,HeaterModel,GeneratorModel,PowerLoadModel,EnergyStorageModel,SensorModel,ControllerModel,NetworkModel,SinkModel,COMPONENT_MODEL_CLASSES} from './components.mjs';
export {CircuitSystemModel,createV2Adapter} from './v2/circuit-system.mjs';
export {createV2ModelDefinition,createV2Component,getV2ModelDescriptor,getV2Descriptor,V2_TYPE_CONTRACTS,V2_MODEL_DESCRIPTORS,V2_VARIANT_DESCRIPTORS,V2_MODEL_FAMILIES,CIRCUIT_MODEL_VERSION,CIRCUIT_PARAMETERS,ENERGY_PARAMETERS,TRACER_FIELDS,ZONE_FIELD_DEFINITIONS} from './v2/contract.mjs';
export {validateV2Definition,validateV2ModelDefinition} from './v2/validation.mjs';
export {EQUATION_UNITS,EQUATION_CONTRACT_VERSION,EQUATION_PHASE_CONTRACTS,EquationRuntime,createEquationRuntime,normalizeEquationBindings,resolveEquationBinding,validateDataSchema,validateSchemaValue} from './equations/index.mjs';
