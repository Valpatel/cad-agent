/** Human and agent discovery share this deterministic metadata-only API. */
import {SCADA_COMPONENTS} from './registry.mjs';
import {queryScadaMetadata,getScadaMetadataFacets} from './selection.mjs';

export {getScadaComponent,getScadaVariants} from './registry.mjs';
export {CAPACITY_PRESETS} from './definitions/power.mjs';

export function findScadaComponents(filters={}) {
  return queryScadaMetadata(SCADA_COMPONENTS,filters);
}

export function getScadaFacets() {
  return getScadaMetadataFacets(SCADA_COMPONENTS);
}
