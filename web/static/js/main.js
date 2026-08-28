// Boot. Fetch the data, stand up the renderer, wire the controls, start ticking.

import { loadBundle } from './bundle.js';
import { Observatory } from './scene.js';
import { Controls } from './controls.js';
import { UI, wireOverlays } from './ui.js';
import { LightPath } from './lightpath.js';
import { Countdown } from './countdown.js';
import { hasWebGL2, mountFallback } from './fallback.js';

const root = document;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

async function json(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return response.json();
}

async function boot() {
  document.documentElement.classList.remove('no-js');

  const [facts, mission] = await Promise.all([json('facts.json'), json('mission.json')]);
  new Countdown({ mission, root });
  wireCopy(facts);

  if (!hasWebGL2()) {
    startFallback(facts);
    return;
  }

  const canvas = root.querySelector('#stage');
  const status = root.querySelector('#loading');

  let model;
  try {
    model = await loadBundle('model/roman.pxob.gz');
  } catch (error) {
    console.error(error);
    startFallback(facts);
    return;
  }

  const observatory = new Observatory(canvas, model, { outline: true });
  const controls = new Controls(observatory, canvas, { reducedMotion });
  const ui = new UI({ facts, mission, root, observatory, controls });
  // Double click and the 0 key reset the camera; the exploded view, the open
  // panel and the pressed view button have to come back with it.
  controls.onReset = () => ui.afterReset();
  const lightPath = new LightPath({
    facts,
    root,
    observatory,
    controls,
    onOpen: () => {
      ui.clearSelection();
      ui.resetExplode();
    },
  });

  const stageWrap = root.querySelector('#app-stage');
  const resize = () => {
    const rect = stageWrap.getBoundingClientRect();
    observatory.resize(rect.width, rect.height);
  };
  new ResizeObserver(resize).observe(stageWrap);
  resize();

  wirePointer(canvas, observatory, ui, controls);
  wireKeys(controls, ui, lightPath);

  if (status) status.hidden = true;
  document.body.classList.add('is-ready');

  // Opt-in handle for poking at the renderer from the console, and for the
  // look-tuning pass where the dither and outline get decided by eye.
  if (location.search.includes('debug')) {
    window.observatory = { observatory, controls, ui, lightPath, model };
  }

  let previous = performance.now();
  const frame = (now) => {
    const delta = Math.min((now - previous) / 1000, 0.1);
    previous = now;
    controls.update(delta);
    ui.refreshReset();
    observatory.render();
    window.requestAnimationFrame(frame);
  };
  window.requestAnimationFrame(frame);
}

/**
 * The no-WebGL path: a pre-rendered orbit instead of the model.
 *
 * The overlays and the light path still work, because neither needs a
 * renderer, and between them they carry the disclaimer and the whole point of
 * the site. Only the controls that steer the 3D scene are taken away, rather
 * than left on screen doing nothing.
 */
function startFallback(facts) {
  document.body.classList.add('is-fallback');
  mountFallback({ root, facts, reducedMotion });
  wireOverlays(root);
  const lightPath = new LightPath({
    facts,
    root,
    observatory: null,
    controls: { snapTo() {} },
  });
  window.addEventListener('keydown', (event) => {
    if (lightPath.dialog.hidden) return;
    if (event.key === 'ArrowRight') lightPath.go(1);
    if (event.key === 'ArrowLeft') lightPath.go(-1);
    if (event.key === 'Escape') lightPath.close();
  });
  document.body.classList.add('is-ready');
}

/** Fill the few chrome slots that the static page leaves for JavaScript. */
function wireCopy(facts) {
  const hint = root.querySelector('#controls-hint');
  if (hint) hint.textContent = facts.ui.controls_hint;
}

function wirePointer(canvas, observatory, ui, controls) {
  let pending = null;
  let raf = 0;

  const flush = () => {
    raf = 0;
    if (!pending) return;
    // Do not try to name a part while the telescope is being spun. The
    // highlight chases the cursor across the model and reads as flicker.
    if (controls.dragging || controls.coasting) {
      pending = null;
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const group = observatory.pick(
      pending.clientX - rect.left,
      pending.clientY - rect.top,
      rect.width,
      rect.height
    );
    ui.setHover(group, pending.clientX, pending.clientY);
    pending = null;
  };

  // Picking costs a draw call, so never more than one per animation frame.
  canvas.addEventListener('pointermove', (event) => {
    if (event.pointerType === 'touch') return;
    pending = event;
    if (!raf) raf = window.requestAnimationFrame(flush);
  });
  canvas.addEventListener('pointerleave', () => ui.setHover(-1, 0, 0));

  let downAt = null;
  canvas.addEventListener('pointerdown', (event) => {
    downAt = { x: event.clientX, y: event.clientY, t: performance.now() };
    ui.setHover(-1, 0, 0);
  });
  canvas.addEventListener('pointerup', (event) => {
    if (!downAt) return;
    const moved = Math.hypot(event.clientX - downAt.x, event.clientY - downAt.y);
    const held = performance.now() - downAt.t;
    downAt = null;
    // A drag is an orbit, not a click. Five pixels of slop for shaky hands.
    if (moved > 5 || held > 700) return;
    const rect = canvas.getBoundingClientRect();
    const group = observatory.pick(
      event.clientX - rect.left,
      event.clientY - rect.top,
      rect.width,
      rect.height
    );
    ui.select(group);
  });
}

function wireKeys(controls, ui, lightPath) {
  window.addEventListener('keydown', (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

    if (event.key === 'Escape') {
      if (ui.closeTopDialog()) event.preventDefault();
      return;
    }
    if (!lightPath.dialog.hidden) {
      if (event.key === 'ArrowRight') {
        lightPath.go(1);
        event.preventDefault();
        return;
      }
      if (event.key === 'ArrowLeft') {
        lightPath.go(-1);
        event.preventDefault();
        return;
      }
    }
    if (controls.handleKey(event)) event.preventDefault();
  });
}

boot().catch((error) => {
  console.error(error);
  const status = root.querySelector('#loading');
  if (status) status.hidden = true;
  document.body.classList.add('is-ready', 'is-broken');
});
