/** Shared 3D interaction, separate from the renderer-independent host. */
export function captureCamera(stage) {
  return { position: stage.camera.position.toArray(), target: stage.controls.target.toArray(), zoom: stage.camera.zoom };
}

export function validateCamera(value) {
  const vector = a => Array.isArray(a) && a.length === 3 && a.every(Number.isFinite);
  if (!value || !vector(value.position) || !vector(value.target) || !Number.isFinite(value.zoom) || value.zoom <= 0
      || value.position.every((v, i) => v === value.target[i])) throw new TypeError('Invalid camera state');
  return value;
}

export function restoreCamera(stage, value) {
  validateCamera(value);
  stage.camera.position.fromArray(value.position); stage.controls.target.fromArray(value.target); stage.camera.zoom = value.zoom;
  stage.camera.updateProjectionMatrix(); stage.controls.update();
}

export function bindStageControls(viewport, stage, fit) {
  const events = new AbortController(), media = matchMedia('(prefers-reduced-motion: reduce)');
  const motion = () => { stage.controls.enableDamping = !media.matches; };
  motion(); media.addEventListener('change', motion);
  viewport.addEventListener('pointerdown', () => viewport.focus({ preventScroll: true }), { signal: events.signal });
  viewport.addEventListener('keydown', event => {
    if (event.target !== viewport && event.target !== stage.renderer.domElement || event.altKey || event.ctrlKey || event.metaKey) return;
    const key = event.key, arrows = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'];
    if (!arrows.includes(key) && !['+', '=', '-', '_', 'Home'].includes(key)) return;
    event.preventDefault(); event.stopPropagation();
    if (key === 'Home') { fit(); return; }
    const offset = stage.camera.position.clone().sub(stage.controls.target), radius = offset.length();
    if (key === '+' || key === '=' || key === '-' || key === '_') {
      const next = Math.min(stage.controls.maxDistance, Math.max(stage.controls.minDistance, radius * (key === '+' || key === '=' ? .85 : 1 / .85)));
      stage.camera.position.copy(stage.controls.target).addScaledVector(offset.normalize(), next);
    } else if (event.shiftKey) {
      const axis = key === 'ArrowLeft' || key === 'ArrowRight' ? 0 : 1;
      const delta = offset.setFromMatrixColumn(stage.camera.matrix, axis).multiplyScalar(radius * .05 * (key === 'ArrowLeft' || key === 'ArrowDown' ? -1 : 1));
      stage.camera.position.add(delta); stage.controls.target.add(delta);
    } else {
      let azimuth = Math.atan2(offset.x, offset.z), polar = Math.acos(Math.max(-1, Math.min(1, offset.y / radius)));
      if (key === 'ArrowLeft') azimuth -= .12; if (key === 'ArrowRight') azimuth += .12;
      if (key === 'ArrowUp') polar -= .12; if (key === 'ArrowDown') polar += .12;
      polar = Math.max(Math.max(.001, stage.controls.minPolarAngle), Math.min(Math.min(Math.PI - .001, stage.controls.maxPolarAngle), polar));
      offset.set(radius * Math.sin(polar) * Math.sin(azimuth), radius * Math.cos(polar), radius * Math.sin(polar) * Math.cos(azimuth));
      stage.camera.position.copy(stage.controls.target).add(offset);
    }
    stage.controls.update();
  }, { signal: events.signal });
  return () => { events.abort(); media.removeEventListener('change', motion); };
}
