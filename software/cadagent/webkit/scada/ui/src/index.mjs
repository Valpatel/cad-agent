/** Public package entry. Imports create no DOM, clock or model session.
 * ScadaWorkspace and mounted ScadaViewer instances own their UI lifecycle. */
export {
  SCADA_COMPONENTS,
  SCADA_CATEGORIES,
  getScadaComponent,
  getScadaVariants,
  normalizeScadaState,
  renderScadaComponent,
} from './symbols/index.mjs';
export {findScadaComponents,getScadaFacets,CAPACITY_PRESETS} from './catalog/discovery.mjs';
export {ScadaWorkspace, renderScadaDialog, renderScadaToolbar} from './workspace/workspace.mjs';
export {ScadaViewer, ScadaCamera, renderScadaDiagram, normalizeViewerDefinition} from './viewer/viewer.mjs';
export {
  SYSTEM_DEFINITION_VERSION,
  validateSystemDefinition,
  resolveBinding,
  resolveComponentState,
} from './contracts/system-definition.mjs';
