// "Follow the light": seven steps from a star to a colour.
//
// Steps two onward draw a schematic over a dimmed model, and say so on screen.
// The source model is the outside of the observatory only, so any picture of
// the coronagraph's insides would be an invention. Drawing it as an obvious
// diagram is the honest way to explain it.

const SVG_NS = 'http://www.w3.org/2000/svg';

// The steps that draw a made-up picture of the instrument. Steps 6 and 7 show a
// colour swatch, which is not a diagram of hardware, so the honesty label would
// be answering a question nobody asked.
const SCHEMATIC_STEPS = new Set(['inside', 'mask', 'filters', 'detector']);

export class LightPath {
  constructor({ facts, root, observatory, controls, onOpen, onClose }) {
    this.facts = facts;
    this.data = facts.lightpath;
    this.root = root;
    this.observatory = observatory;
    this.controls = controls;
    this.onOpen = onOpen;
    this.onClose = onClose;

    this.dialog = root.querySelector('#lightpath');
    this.stage = root.querySelector('#lightpath-stage');
    this.scroll = root.querySelector('#lightpath-scroll');
    this.title = root.querySelector('#lightpath-title');
    this.body = root.querySelector('#lightpath-body');
    this.note = root.querySelector('#lightpath-note');
    this.counter = root.querySelector('#lightpath-counter');
    this.warning = root.querySelector('#lightpath-warning');
    this.opener = root.querySelector('#lightpath-open');
    this.index = 0;

    // Clicking the dimmed surround closes it, the way a modal should.
    this.dialog?.addEventListener('mousedown', (event) => {
      if (event.target === this.dialog) this.close();
    });

    root.querySelector('#lightpath-open')?.addEventListener('click', () => this.open());
    root.querySelector('#lightpath-next')?.addEventListener('click', () => this.go(1));
    root.querySelector('#lightpath-back')?.addEventListener('click', () => this.go(-1));
    this.dialog?.querySelectorAll('[data-close]').forEach((button) => {
      button.addEventListener('click', () => this.close());
    });
  }

  open() {
    this.index = 0;
    this.dialog.hidden = false;
    this.dialog.setAttribute('aria-hidden', 'false');
    this._setBackgroundInert(true);
    // Put the observatory side on so the diagram has something to sit against.
    this.controls.snapTo('front');
    this.onOpen?.();
    this.render();
    // preventScroll matters: without it the browser scrolls Next into view
    // inside the dialog, which on a laptop pushed the close button off the top.
    this.root.querySelector('#lightpath-next')?.focus({ preventScroll: true });
  }

  close() {
    this.dialog.hidden = true;
    this.dialog.setAttribute('aria-hidden', 'true');
    this._setBackgroundInert(false);
    this.onClose?.();
    // Hand focus back to the control that opened this, not to the document.
    this.opener?.focus();
  }

  /** Take the scene and the controls out of the tab order while this is up. */
  _setBackgroundInert(inert) {
    for (const selector of ['#app-stage', '.hud-top', '.hud-bottom', '#panel']) {
      const node = this.root.querySelector(selector);
      if (!node) continue;
      if (inert) node.setAttribute('inert', '');
      else node.removeAttribute('inert');
    }
  }

  go(delta) {
    const next = this.index + delta;
    if (next < 0 || next >= this.data.steps.length) return;
    this.index = next;
    this.render();
  }

  render() {
    const step = this.data.steps[this.index];
    this.title.textContent = step.title;
    this.body.replaceChildren(document.createTextNode(step.text));
    this.counter.textContent =
      `${this.facts.ui.lightpath_step} ${this.index + 1} ${this.facts.ui.lightpath_of} ` +
      `${this.data.steps.length}`;

    const schematic = SCHEMATIC_STEPS.has(step.id);
    this.warning.textContent = schematic ? this.data.schematic_warning.text : '';
    this.warning.hidden = !schematic;

    // The caveats on steps four and five are the pinned ones. A title attribute
    // is invisible to anybody on a touch screen, so they go on the page.
    const note = step.source_note || (this.index === 0 ? this.data.intro.text : '');
    this.note.textContent = note;
    this.note.hidden = !note;

    if (this.scroll) this.scroll.scrollTop = 0;

    const last = this.index === this.data.steps.length - 1;
    this.root.querySelector('#lightpath-back').disabled = this.index === 0;
    this.root.querySelector('#lightpath-next').disabled = last;

    this.stage.replaceChildren(this._diagram(step.id));
    this._renderSources(step);
    this._renderDots();
  }

  /** One dot per step, so the length of the thing is visible at a glance. */
  _renderDots() {
    const holder = this.root.querySelector('#lightpath-dots');
    if (!holder) return;
    holder.replaceChildren(
      ...this.data.steps.map((_, i) => {
        const dot = document.createElement('span');
        dot.className = i === this.index ? 'dot dot-on' : 'dot';
        return dot;
      })
    );
  }

  /**
   * Every step's claim carries its source, the same way the component panels do.
   * The data was always in facts.json; this overlay just used to ignore it.
   */
  _renderSources(step) {
    const holder = this.root.querySelector('#lightpath-sources');
    if (!holder) return;
    const source = this.facts.sources[step.source];
    holder.replaceChildren();
    if (!source) return;
    const link = document.createElement('a');
    link.className = 'step-source';
    link.href = source.url;
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = source.label;
    if (step.source_note) link.title = step.source_note;
    link.setAttribute(
      'aria-label',
      step.source_note ? `Source: ${source.label}. ${step.source_note}` : `Source: ${source.label}`
    );
    holder.append(link);
  }

  _diagram(id) {
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 300 150');
    svg.setAttribute('class', 'diagram');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', this.data.steps[this.index].title);
    const draw = {
      arrive: () => this._arrive(svg),
      inside: () => this._inside(svg),
      mask: () => this._mask(svg),
      filters: () => this._filters(svg),
      detector: () => this._detector(svg),
      colour: () => this._colour(svg),
      finale: () => this._finale(svg),
    }[id];
    draw?.();
    return svg;
  }

  _line(svg, x1, y1, x2, y2, cls, width = 2) {
    const line = document.createElementNS(SVG_NS, 'line');
    line.setAttribute('x1', x1);
    line.setAttribute('y1', y1);
    line.setAttribute('x2', x2);
    line.setAttribute('y2', y2);
    line.setAttribute('class', cls);
    line.setAttribute('stroke-width', width);
    svg.append(line);
    return line;
  }

  _box(svg, x, y, w, h, cls) {
    const rect = document.createElementNS(SVG_NS, 'rect');
    rect.setAttribute('x', x);
    rect.setAttribute('y', y);
    rect.setAttribute('width', w);
    rect.setAttribute('height', h);
    rect.setAttribute('class', cls);
    svg.append(rect);
    return rect;
  }

  _text(svg, x, y, value, cls = 'diagram-label') {
    const node = document.createElementNS(SVG_NS, 'text');
    node.setAttribute('x', x);
    node.setAttribute('y', y);
    node.setAttribute('class', cls);
    node.textContent = value;
    svg.append(node);
    return node;
  }

  _arrive(svg) {
    const label = this.data.diagram;
    this._text(svg, 30, 40, label.star);
    this._text(svg, 30, 116, label.planet);
    // Both beams run into the aperture rather than stopping just short of it.
    this._line(svg, 52, 34, 246, 64, 'beam-star', 5);
    this._line(svg, 52, 110, 246, 80, 'beam-planet', 1.5);
    this._box(svg, 238, 42, 16, 62, 'aperture');
    this._text(svg, 246, 126, label.aperture);
  }

  _inside(svg) {
    const label = this.data.diagram;
    const bay = { x: 130, w: 160 };
    const centre = bay.x + bay.w / 2;
    this._box(svg, bay.x, 28, bay.w, 92, 'bay');
    this._line(svg, 8, 62, 152, 70, 'beam-star', 5);
    this._line(svg, 8, 92, 152, 80, 'beam-planet', 1.5);
    this._text(svg, centre, 64, label.bay);
    this._text(svg, centre, 84, label.bay_note, 'diagram-small');
  }

  _mask(svg) {
    const label = this.data.diagram;
    this._line(svg, 8, 64, 148, 70, 'beam-star', 5);
    this._box(svg, 146, 34, 10, 74, 'mask');
    // Drawn after the mask, so the surviving beam visibly crosses it. Drawn
    // before, the opaque mask cut the planet's line in half and the picture
    // said the opposite of the sentence beside it.
    this._line(svg, 8, 88, 292, 78, 'beam-planet', 1.5);
    this._text(svg, 151, 126, label.mask);
    this._text(svg, 250, 64, label.planet);
  }

  _filters(svg) {
    const label = this.data.diagram;
    const bands = this.data.bands;
    const width = 56;
    const gap = 8;
    const left = 150 - (bands.length * width + (bands.length - 1) * gap) / 2;
    this._text(svg, 150, 24, label.wheel);
    bands.forEach((band, i) => {
      const x = left + i * (width + gap);
      this._box(svg, x, 40, width, 54, band.supported ? 'filter' : 'filter filter-off');
      const numberClass = band.supported ? 'diagram-band' : 'diagram-band diagram-band-off';
      this._text(svg, x + width / 2, 74, `${band.nm}`, numberClass);
      const caption = band.supported ? band.width_short : label.not_tested;
      this._text(svg, x + width / 2, 112, caption, 'diagram-small');
    });
  }

  _detector(svg) {
    const label = this.data.diagram;
    const supported = this.data.bands.filter((b) => b.supported);
    const width = 54;
    const gap = 26;
    const left = 150 - (supported.length * width + (supported.length - 1) * gap) / 2;
    this._text(svg, 150, 22, label.counts);
    supported.forEach((band, i) => {
      const x = left + i * (width + gap);
      const mid = x + width / 2;
      this._line(svg, mid, 30, mid, 52, 'beam-planet', 1.5);
      this._box(svg, x, 52, width, 40, 'detector');
      // A blank readout rather than an invented number: nobody has measured
      // these, which is the whole point the last step lands on.
      this._line(svg, x + 10, 72, x + width - 10, 72, 'readout', 1.5);
      this._text(svg, mid, 110, `${band.nm} nm`, 'diagram-small');
    });
    this._text(svg, 150, 132, label.readout, 'diagram-small');
  }

  _colour(svg) {
    const hero = this.data.hero_planet;
    const label = this.data.diagram;
    this._text(svg, 150, 24, label.bands_sum, 'diagram-small');
    if (!hero.hex) {
      this._box(svg, 100, 38, 100, 62, 'swatch swatch-pending');
      return;
    }
    // One swatch, because the sentence beside it says one swatch.
    const cell = this._box(svg, 100, 38, 100, 62, 'swatch-filled');
    cell.setAttribute('fill', hero.hex);
    this._text(svg, 150, 118, hero.short_name || hero.name);
    this._text(svg, 150, 136, label.predicted, 'diagram-small');
  }

  _finale(svg) {
    const hero = this.data.hero_planet;
    const label = this.data.diagram;
    // What we have beside what nobody has: the predicted palette next to an
    // empty measured slot. Step six already showed the swatch, so repeating it
    // here made the finale look like a duplicate.
    const stops = hero.palette && hero.palette.length ? hero.palette : [hero.hex];
    const cellWidth = 22;
    const left = 78 - (stops.length * cellWidth) / 2;
    stops.forEach((hex, i) => {
      const cell = this._box(svg, left + i * cellWidth, 40, cellWidth, 58, 'swatch-filled');
      cell.setAttribute('fill', hex);
    });
    this._text(svg, 78, 118, label.predicted, 'diagram-small');

    this._box(svg, 178, 40, 100, 58, 'swatch swatch-pending');
    this._text(svg, 228, 74, label.not_yet, 'diagram-small');
    this._text(svg, 228, 118, label.measured, 'diagram-small');
  }
}
