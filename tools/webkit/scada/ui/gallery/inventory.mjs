// Pure catalog expectations for read-only image manifest validation.
import {SCADA_COMPONENTS, getScadaVariants, normalizeScadaState, getScadaComponent} from '../../../../../software/cadagent/webkit/scada/ui/src/catalog/registry.mjs';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';

export function galleryInventory(samples) {
  const selections = SCADA_COMPONENTS.flatMap(component => [
    {type: component.type},
    ...getScadaVariants(component.type).map(variant => ({type: component.type, variant: variant.id})),
  ]);
  return [...selections, ...samples].map(selection => {
    const options = selection.variant ? {variant: selection.variant} : {};
    const descriptor = getScadaComponent(selection.type, options);
    const stem = selection.type + (selection.variant ? '--' + selection.variant : '') + (selection.sample ? '--' + selection.sample : '');
    const path = selection.sample
      ? `img/states/${selection.group}/${stem}.svg`
      : `img/symbols/${descriptor.category}/${selection.type}/${selection.variant ?? 'default'}.svg`;
    if (selection.sample && !/^[a-z-]+$/.test(selection.group ?? '')) throw new TypeError('State samples require a semantic group.');
    return {
      type: selection.type, variant: selection.variant ?? null, sample: selection.sample ?? null,
      path, category: descriptor.category,
      label: descriptor.label, variantLabel: descriptor.selectedVariant?.label ?? null,
      state: normalizeScadaState(selection.type, selection.state ?? {}, options),
      stateFields: descriptor.stateFields, description: descriptor.description,
      stateLabel: selection.stateLabel ?? 'Active illustrative preview',
      expectedMotion: selection.expectedMotion ?? null,
    };
  });
}

if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const samples = JSON.parse(fs.readFileSync(new URL('samples.json', import.meta.url), 'utf8'));
  process.stdout.write(JSON.stringify(galleryInventory(samples)));
}
