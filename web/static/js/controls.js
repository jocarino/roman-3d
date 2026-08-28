// Orbit, zoom and the five snap views. Written by hand rather than pulled from
// three's examples, because the snap buttons, the keyboard map and the
// reduced-motion behaviour are all part of the design rather than defaults.

const DEG = Math.PI / 180;
const MIN_ELEVATION = -88;
const MAX_ELEVATION = 88;
const MIN_ZOOM = 0.55;
const MAX_ZOOM = 4.5;

// Matches pipeline/render.py SNAP_VIEWS, so a snap view on the site frames the
// model exactly as the offline fallback frames do.
export const SNAP_VIEWS = {
  front: { azimuth: 0, elevation: 14 },
  right: { azimuth: 90, elevation: 14 },
  back: { azimuth: 180, elevation: 14 },
  left: { azimuth: 270, elevation: 14 },
  top: { azimuth: 0, elevation: 88 },
};

export const SNAP_ORDER = ['front', 'right', 'back', 'left', 'top'];

export class Controls {
  constructor(observatory, element, { reducedMotion = false, onReset = null } = {}) {
    this.observatory = observatory;
    this.element = element;
    this.reducedMotion = reducedMotion;
    // Fired by every reset route (button, double click, the 0 key) so the UI
    // can put the exploded view and the panel back at the same time.
    this.onReset = onReset;

    this.azimuth = 24;
    this.elevation = 18;
    this.zoom = 1;
    this.target = { azimuth: 24, elevation: 18, zoom: 1 };
    this.velocity = { azimuth: 0, elevation: 0 };

    this.autoOrbit = !reducedMotion;
    this.dragging = false;
    this.pointerId = null;
    this.last = { x: 0, y: 0 };
    this.pinch = null;

    this.distance = Math.hypot(...observatory.dims) * 3;
    this._bind();
    this.apply(true);
  }

  _bind() {
    const el = this.element;
    el.style.touchAction = 'none';

    el.addEventListener('pointerdown', (event) => {
      if (event.button !== 0 && event.pointerType === 'mouse') return;
      this.dragging = true;
      this.autoOrbit = false;
      this.pointerId = event.pointerId;
      this.last = { x: event.clientX, y: event.clientY };
      el.setPointerCapture(event.pointerId);
    });

    el.addEventListener('pointermove', (event) => {
      if (!this.dragging || event.pointerId !== this.pointerId) return;
      const dx = event.clientX - this.last.x;
      const dy = event.clientY - this.last.y;
      this.last = { x: event.clientX, y: event.clientY };
      this.target.azimuth -= dx * 0.4;
      this.target.elevation = clamp(
        this.target.elevation + dy * 0.35,
        MIN_ELEVATION,
        MAX_ELEVATION
      );
      if (!this.reducedMotion) {
        this.velocity.azimuth = -dx * 0.4;
        this.velocity.elevation = dy * 0.35;
      }
    });

    const release = (event) => {
      if (event.pointerId !== this.pointerId) return;
      this.dragging = false;
      this.pointerId = null;
    };
    el.addEventListener('pointerup', release);
    el.addEventListener('pointercancel', release);

    el.addEventListener(
      'wheel',
      (event) => {
        event.preventDefault();
        this.autoOrbit = false;
        const factor = Math.exp(-event.deltaY * 0.0016);
        this.target.zoom = clamp(this.target.zoom * factor, MIN_ZOOM, MAX_ZOOM);
      },
      { passive: false }
    );

    el.addEventListener('dblclick', () => this.reset());  // also snaps the exploded view back

    // Two-finger pinch. Tracked separately from the single-pointer drag so a
    // pinch never also spins the model.
    const active = new Map();
    el.addEventListener('pointerdown', (e) => active.set(e.pointerId, e));
    el.addEventListener('pointermove', (e) => {
      if (!active.has(e.pointerId)) return;
      active.set(e.pointerId, e);
      if (active.size !== 2) return;
      this.dragging = false;
      const [a, b] = [...active.values()];
      const spread = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      if (this.pinch) {
        this.target.zoom = clamp((this.pinch.zoom * spread) / this.pinch.spread, MIN_ZOOM, MAX_ZOOM);
      } else {
        this.pinch = { spread, zoom: this.target.zoom };
      }
    });
    const drop = (e) => {
      active.delete(e.pointerId);
      if (active.size < 2) this.pinch = null;
    };
    el.addEventListener('pointerup', drop);
    el.addEventListener('pointercancel', drop);
  }

  /** Keyboard map, wired from main so the handler can be shared with the UI. */
  handleKey(event) {
    const step = event.shiftKey ? 15 : 5;
    switch (event.key) {
      case 'ArrowLeft':
        this.nudge(-step, 0);
        return true;
      case 'ArrowRight':
        this.nudge(step, 0);
        return true;
      case 'ArrowUp':
        this.nudge(0, -step);
        return true;
      case 'ArrowDown':
        this.nudge(0, step);
        return true;
      case '+':
      case '=':
        this.zoomBy(1.18);
        return true;
      case '-':
      case '_':
        this.zoomBy(1 / 1.18);
        return true;
      case '0':
        this.reset();
        return true;
      default:
        break;
    }
    const slot = Number(event.key);
    if (Number.isInteger(slot) && slot >= 1 && slot <= SNAP_ORDER.length) {
      this.snapTo(SNAP_ORDER[slot - 1]);
      return true;
    }
    return false;
  }

  nudge(dAzimuth, dElevation) {
    this.autoOrbit = false;
    this.target.azimuth += dAzimuth;
    this.target.elevation = clamp(this.target.elevation + dElevation, MIN_ELEVATION, MAX_ELEVATION);
  }

  zoomBy(factor) {
    this.autoOrbit = false;
    this.target.zoom = clamp(this.target.zoom * factor, MIN_ZOOM, MAX_ZOOM);
  }

  snapTo(name) {
    const view = SNAP_VIEWS[name];
    if (!view) return;
    this.autoOrbit = false;
    this.velocity.azimuth = 0;
    this.velocity.elevation = 0;
    // Take the short way round rather than unwinding several turns.
    const current = this.target.azimuth;
    const delta = ((((view.azimuth - current) % 360) + 540) % 360) - 180;
    this.target.azimuth = current + delta;
    this.target.elevation = view.elevation;
    this.target.zoom = 1;
    if (this.reducedMotion) this.apply(true);
  }

  reset({ notify = true } = {}) {
    this.autoOrbit = !this.reducedMotion;
    this.target = { azimuth: 24, elevation: 18, zoom: 1 };
    this.velocity = { azimuth: 0, elevation: 0 };
    if (this.reducedMotion) this.apply(true);
    if (notify) this.onReset?.();
  }

  update(delta) {
    if (this.autoOrbit && !this.dragging) {
      this.target.azimuth += delta * 4.5;
    }
    if (!this.dragging && !this.reducedMotion) {
      this.target.azimuth += this.velocity.azimuth * delta * 2.4;
      this.target.elevation = clamp(
        this.target.elevation + this.velocity.elevation * delta * 2.4,
        MIN_ELEVATION,
        MAX_ELEVATION
      );
      this.velocity.azimuth *= Math.pow(0.02, delta);
      this.velocity.elevation *= Math.pow(0.02, delta);
      if (Math.abs(this.velocity.azimuth) < 0.01) this.velocity.azimuth = 0;
      if (Math.abs(this.velocity.elevation) < 0.01) this.velocity.elevation = 0;
    }

    const ease = this.reducedMotion ? 1 : 1 - Math.pow(0.0001, delta);
    this.azimuth += (this.target.azimuth - this.azimuth) * ease;
    this.elevation += (this.target.elevation - this.elevation) * ease;
    this.zoom += (this.target.zoom - this.zoom) * ease;
    this.apply();
  }

  apply(immediate = false) {
    if (immediate) {
      this.azimuth = this.target.azimuth;
      this.elevation = this.target.elevation;
      this.zoom = this.target.zoom;
    }
    const az = this.azimuth * DEG;
    const el = this.elevation * DEG;
    const camera = this.observatory.camera;
    camera.position.set(
      Math.cos(el) * Math.sin(az) * this.distance,
      Math.sin(el) * this.distance,
      Math.cos(el) * Math.cos(az) * this.distance
    );
    camera.up.set(0, 1, 0);
    if (Math.abs(this.elevation) > 87.5) camera.up.set(0, 0, -1);
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld();
    this.observatory.frameCamera(this.zoom);
  }
}

function clamp(value, low, high) {
  return Math.min(high, Math.max(low, value));
}
