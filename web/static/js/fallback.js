// No-WebGL fallback: a pre-rendered orbit, scrubbable.
//
// The frames come out of the same offline renderer that made the contact sheet,
// so someone on a browser without 3D sees the same observatory in the same
// palette, just without the freedom to spin it themselves.

const FRAME_COUNT = 24;

export function hasWebGL2() {
  try {
    const canvas = document.createElement('canvas');
    return Boolean(canvas.getContext('webgl2'));
  } catch (error) {
    return false;
  }
}

export function mountFallback({ root, facts, framePath = 'frames', reducedMotion = false }) {
  const holder = root.querySelector('#fallback');
  const image = root.querySelector('#fallback-frame');
  const scrub = root.querySelector('#fallback-scrub');
  const notice = root.querySelector('#fallback-notice');
  if (!holder || !image) return null;

  root.querySelector('#app-stage')?.setAttribute('hidden', '');
  holder.hidden = false;
  if (notice) notice.textContent = facts.ui.no_webgl;

  let index = 0;
  const show = (next) => {
    index = ((next % FRAME_COUNT) + FRAME_COUNT) % FRAME_COUNT;
    image.src = `${framePath}/orbit-${String(index).padStart(2, '0')}.png`;
    image.alt = `${facts.ui.frame_label} ${index + 1} / ${FRAME_COUNT}`;
    if (scrub) {
      scrub.value = String(index);
      scrub.style.setProperty('--fill', `${(index / (FRAME_COUNT - 1)) * 100}%`);
    }
  };

  scrub?.addEventListener('input', () => show(Number(scrub.value)));
  show(0);

  if (!reducedMotion) {
    window.setInterval(() => show(index + 1), 110);
  }
  return { show };
}
