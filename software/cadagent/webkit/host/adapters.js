/** Concrete 3D adapters. Import viewer-host.js alone for a renderer-independent shell. */
import * as THREE from 'three';
import { createViewer } from '../model/viewer.js';
import { createFileViewer } from '../files/file-viewer.js';
import { createViewerHost } from './viewer-host.js';
import { bindStageControls, captureCamera, restoreCamera, validateCamera } from './stage-controls.js';

function stateFor(kind, documentId, value) {
  if (!value || value.version !== 1 || value.kind !== kind || value.documentId !== documentId) throw new Error('View state belongs to another loaded document');
  validateCamera(value.camera); return value;
}

export function createModelHost(container, { title = 'Assembly model', manifestUrl, ...options } = {}) {
  return createViewerHost(container, { title, signal: options.signal,
    async mount({ viewport, inspector, signal, onProgress, onSelect, onState }) {
      let selector;
      function syncSelection(state) {
        if (!selector) return;
        selector.value = state.selected ?? '';
        for (const option of selector.options) option.disabled = !!option.value && (!state.visible.includes(option.value) || state.isolate !== null && !state.isolate.includes(option.value));
      }
      const viewer = await createViewer({ ...options, app: viewport, panel: inspector, title: null, manifestUrl, signal,
        embedded: true, onProgress, onSelect: value => { if (selector) selector.value = value ?? ''; onSelect(value); },
        onStateChange: state => { syncSelection(state); onState(state); }, onError: error => onState({ state: 'error', message: error.message }) });
      let unbind;
      try {
        const documentId = crypto.randomUUID();
        // Match the contained surface instead of compositing shadows over a page background.
        viewer.stage.setPalette({ background: getComputedStyle(viewport).getPropertyValue('--viewer-bg').trim() || '#0e1b28' });
        const fit = () => viewer.frameParts();
        const label = document.createElement('label'); label.textContent = 'Part selection';
        selector = document.createElement('select'); selector.setAttribute('aria-label', 'Part selection');
        for (const [value, text] of [['', 'No selection'], ...viewer.parts.map(part => [part.name, part.name])]) {
          const option = document.createElement('option'); option.value = value; option.textContent = text; selector.append(option);
        }
        syncSelection(viewer.getState());
        selector.onchange = () => {
          if (selector.selectedOptions[0]?.disabled) { syncSelection(viewer.getState()); return; }
          viewer.setSelection(selector.value || null);
        };
        label.append(selector); inspector.prepend(label);
        unbind = bindStageControls(viewport, viewer.stage, fit);
        return { fit, select: value => viewer.setSelection(value),
          getViewState: () => ({ version: 1, kind: 'assembly', documentId, camera: captureCamera(viewer.stage), selection: viewer.getState().selected, domain: viewer.getState() }),
          restoreViewState(value) {
            stateFor('assembly', documentId, value);
            if (value.selection !== value.domain?.selected) throw new Error('Inconsistent assembly selection');
            viewer.applyState(value.domain); restoreCamera(viewer.stage, value.camera);
          },
          dispose() { unbind(); viewer.dispose(); },
        };
      } catch (error) { unbind?.(); viewer.dispose(); throw error; }
    },
  });
}

export function createFileHost(container, { title = 'Original CAD file', file, ...options } = {}) {
  return createViewerHost(container, { title, signal: options.signal,
    async mount({ viewport, inspector, signal, onProgress, onSelect, onState }) {
      signal.throwIfAborted();
      let viewer, unbind, selection = null, lastError;
      const events = new AbortController(), documentId = crypto.randomUUID();
      const dispose = () => { events.abort(); unbind?.(); viewer?.dispose(); signal.removeEventListener('abort', dispose); };
      signal.addEventListener('abort', dispose, { once: true });
      try {
        viewer = createFileViewer(viewport, { ...options, embedded: true,
          onState(event) { lastError = event.state === 'error' ? event.message : lastError; if (event.state === 'loading') onProgress(event.message); onState(event); },
          onError: error => onState({ state: 'error', message: error.message }) });
        if (!await viewer.load(file)) throw new Error(lastError || 'Original file could not be loaded');
        signal.throwIfAborted();
        const meshes = viewer.model.children.filter(node => node.isMesh);
        const controls = document.createElement('label'); controls.textContent = 'Mesh selection';
        const selectBox = document.createElement('select'); selectBox.setAttribute('aria-label', 'Mesh selection');
        const empty = document.createElement('option'); empty.value = ''; empty.textContent = 'No selection'; selectBox.append(empty);
        meshes.forEach((mesh, index) => { const option = document.createElement('option'); option.value = `mesh:${index}`; option.textContent = mesh.name || `Mesh ${index + 1}`; selectBox.append(option); });
        controls.append(selectBox); inspector.append(controls);
        const note = document.createElement('p'); note.className = 'hud-note'; note.textContent = `${viewer.info.sourceName} · ${viewer.info.triangles.toLocaleString()} triangles. Mesh IDs are local to this loaded document.`; inspector.append(note);
        function select(value) {
          if (value !== null && !meshes.some((_, index) => value === `mesh:${index}`)) throw new Error('Unknown file mesh selection');
          selection = value; selectBox.value = value ?? '';
          meshes.forEach((mesh, index) => { for (const material of [].concat(mesh.material)) material.emissive.setHex(value === `mesh:${index}` ? 0x005588 : 0); });
          onSelect(value); return value;
        }
        selectBox.addEventListener('change', () => select(selectBox.value || null), { signal: events.signal });
        let down;
        const canvas = viewer.stage.renderer.domElement, ray = new THREE.Raycaster(), point = new THREE.Vector2();
        canvas.addEventListener('pointerdown', event => { down = event.button === 0 ? [event.clientX, event.clientY, event.pointerId] : null; }, { signal: events.signal });
        canvas.addEventListener('pointerup', event => {
          const start = down; down = null;
          if (!start || event.pointerId !== start[2] || Math.hypot(event.clientX - start[0], event.clientY - start[1]) > 5) return;
          const rect = canvas.getBoundingClientRect(); point.set(2 * (event.clientX - rect.left) / rect.width - 1, 1 - 2 * (event.clientY - rect.top) / rect.height);
          ray.setFromCamera(point, viewer.stage.camera); const object = ray.intersectObjects(meshes, false)[0]?.object;
          select(object ? `mesh:${meshes.indexOf(object)}` : null);
        }, { signal: events.signal });
        canvas.addEventListener('pointercancel', () => { down = null; }, { signal: events.signal });
        unbind = bindStageControls(viewport, viewer.stage, () => viewer.fit());
        return { fit: () => viewer.fit(), select,
          getViewState: () => ({ version: 1, kind: 'file', documentId, camera: captureCamera(viewer.stage), selection }),
          restoreViewState(value) { stateFor('file', documentId, value); select(value.selection); restoreCamera(viewer.stage, value.camera); },
          dispose,
        };
      } catch (error) { dispose(); throw error; }
    },
  });
}
