import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from '../dependencies.mjs';
import {renderScadaComponent} from '../../../../software/cadagent/webkit/scada/ui/src/symbols/index.mjs';

const points = path => (path.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number).reduce((pairs, value, i, values) => {
  if (i % 2 === 0) pairs.push([value, values[i + 1]]);
  return pairs;
}, []);
const area = polygon => Math.abs(polygon.reduce((sum, a, i) => {
  const b = polygon[(i + 1) % polygon.length];
  return sum + a[0] * b[1] - b[0] * a[1];
}, 0)) / 2;
const inside = (point, polygon) => {
  const sides = polygon.map((a, i) => {
    const b = polygon[(i + 1) % polygon.length];
    return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]);
  });
  return sides.every(value => value >= -.1) || sides.every(value => value <= .1);
};

test('roof vent stays hinged, seals its opening and keeps its actuator attached throughout travel', () => {
  let hinge, previousHeight = Infinity;
  for (const opening of [0, 20, 50, 80, 100]) {
    const dom = new JSDOM(renderScadaComponent('greenhouse-vent', {state:{opening}}));
    const root = dom.window.document;
    const panel = points(root.querySelector('.scada-agri-vent-panel > path').getAttribute('d'));
    const rod = points(root.querySelector('.scada-agri-vent-actuator > path').getAttribute('d'));
    hinge ??= panel[0];
    assert.deepEqual(panel[0], hinge, 'the ridge bearing cannot drift as the panel opens');
    assert.ok(panel[1][1] < previousHeight, 'the free edge rises with increasing opening');
    previousHeight = panel[1][1];
    assert.ok(area(panel) > 600, 'the glazed panel remains a visible surface, never a collapsed line');
    assert.ok(panel.every(([x,y]) => x >= 0 && x <= 180 && y >= 0 && y <= 136));
    assert.ok(inside(rod.at(-1), panel), 'the piston end stays attached to the panel');
    if (!opening) {
      const aperture = points(root.querySelector('.scada-agri-vent-aperture').getAttribute('d'));
      assert.deepEqual(panel.toSorted(), aperture.toSorted(), 'a closed panel meets its complete roof opening');
      assert.equal(root.querySelector('.scada-agri-art').dataset.agriActive, 'false');
    }
    dom.window.close();
  }
});

test('nutrient film descends toward the return and roots remain inside the channel cutaway', () => {
  const dom = new JSDOM(renderScadaComponent('nft-channel', {id:'first'}) + renderScadaComponent('nft-channel', {id:'second'}));
  const root = dom.window.document;
  const clips = [...root.querySelectorAll('clipPath')];
  assert.equal(new Set(clips.map(clip => clip.id)).size, clips.length, 'instances never share clipping IDs');
  for (const component of root.querySelectorAll('.scada-component')) {
    const film = component.querySelector('.scada-agri-nft-stream');
    const direction = points(film.getAttribute('d'));
    assert.ok(direction[1][0] > direction[0][0] && direction[1][1] > direction[0][1], 'flow travels left to right down the pictured slope');
    const cutaway = film.parentElement;
    const id = cutaway.getAttribute('clip-path').slice(5, -1);
    assert.ok(component.querySelector(`[id="${id}"]`), 'the cutaway resolves inside its own equipment instance');
    assert.ok(cutaway.querySelectorAll('.scada-agri-nft-root').length >= 2, 'exposed roots and film share the same cutaway boundary');
  }
  dom.window.close();
});
