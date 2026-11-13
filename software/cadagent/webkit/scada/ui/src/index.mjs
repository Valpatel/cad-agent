/** Public package entry. Imports create no DOM, clock or model session.
 * ScadaWorkspace and mounted ScadaViewer instances own their UI lifecycle. */
export {
  SCADA_COMPONENTS,
  SCADA_CATEGORIES,
  getScadaComponent,
  getScadaVariants,
  normalizeScadaState,
  renderScadaComponent,
} from './scada-components.mjs';
export {findScadaComponents,getScadaFacets,CAPACITY_PRESETS} from './scada-catalog.mjs';
export {ScadaWorkspace, renderScadaDialog, renderScadaToolbar} from './scada-workspace.mjs';
export {ScadaViewer, ScadaCamera, renderScadaDiagram, normalizeViewerDefinition} from './scada-viewer.mjs';
export {
  SYSTEM_DEFINITION_VERSION,
  validateSystemDefinition,
  resolveBinding,
  resolveComponentState,
} from './system-definition.mjs';
