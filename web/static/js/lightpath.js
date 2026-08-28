// "Follow the light": seven steps from a star to a colour.
//
// Steps two onward draw a schematic over a dimmed model, and say so on screen.
// The source model is the outside of the observatory only, so any picture of
// the coronagraph's insides would be an invention. Drawing it as an obvious
// diagram is the honest way to explain it.

const SVG_NS = 'http://www.w3.org/2000/svg';

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
    this.title = root.querySelector('#lightpath-title');
    this.body = root.querySelector('#lightpath-body');
    this.counter = root.querySelector('#lightpath-counter');
    this.warning = root.querySelector('#lightpath-warning');
    this.index = 0;

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
    // Put the observatory side on so the diagram has something to sit against.
    this.controls.snapTo('front');
    this.onOpen?.();
    this.render();
    this.root.querySelector('#lightpath-next')?.focus();
  }

  close() {
    this.dialog.hidden = true;
    this.dialog.setAttribute('aria-hidden', 'true');
    this.onClose?.();
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

    const schematic = this.index >= 1;
    this.warning.hidden = !schematic;
    this.warning.textContent = schematic ? this.data.schematic_warning.text : '';
    this.dialog.classList.toggle('is-schematic', schematic);

    this.root.querySelector('#lightpath-back').disabled = this.index === 0;
    this.root.querySelector('#lightpath-next').disabled =
      this.index === this.data.steps.length - 1;

    this.stage.replaceChildren(this._diagram(step.id));
  }

  _diagram(id) {
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 320 150');
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
    // Anchored middle like every other label, so keep them clear of the edge.
    this._text(svg, 26, 40, label.star);
    this._text(svg, 26, 104, label.planet);
    this._line(svg, 44, 34, 250, 62, 'beam-star', 5);
    this._line(svg, 44, 98, 250, 74, 'beam-planet', 1);
    this._box(svg, 252, 44, 14, 50, 'aperture');
    this._text(svg, 236, 128, label.aperture);
  }

  _inside(svg) {
    this._line(svg, 4, 60, 120, 68, 'beam-star', 5);
    this._line(svg, 4, 86, 120, 76, 'beam-planet', 1);
    this._box(svg, 122, 30, 180, 90, 'bay');
    this._text(svg, 172, 52, this.data.diagram.bay);
    this._text(svg, 172, 70, this.data.diagram.bay_note);
  }

  _mask(svg) {
    this._line(svg, 4, 66, 140, 70, 'beam-star', 5);
    this._line(svg, 4, 84, 300, 76, 'beam-planet', 1);
    this._box(svg, 140, 40, 10, 66, 'mask');
    this._text(svg, 112, 126, this.data.diagram.mask);
    this._text(svg, 250, 62, this.data.diagram.planet);
  }

  _filters(svg) {
    const gap = 68;
    this.data.bands.forEach((band, i) => {
      const x = 22 + i * gap;
      this._box(svg, x, 40, 52, 52, band.supported ? 'filter' : 'filter filter-off');
      this._text(svg, x + 26, 70, `${band.nm}`, 'diagram-band');
      const caption = band.supported ? band.width : this.data.diagram.not_tested;
      this._text(svg, x + 26, 106, caption, 'diagram-small');
    });
    this._text(svg, 160, 24, this.data.diagram.wheel);
  }

  _detector(svg) {
    const supported = this.data.bands.filter((b) => b.supported);
    supported.forEach((band, i) => {
      const x = 30 + i * 92;
      this._line(svg, x + 20, 30, x + 20, 62, 'beam-planet', 1);
      this._box(svg, x, 62, 40, 34, 'detector');
      this._text(svg, x + 20, 112, `${band.nm} nm`, 'diagram-small');
    });
    this._text(svg, 160, 20, this.data.diagram.counts);
  }

  _colour(svg) {
    const hero = this.data.hero_planet;
    this._box(svg, 108, 34, 104, 74, hero.hex ? 'swatch' : 'swatch swatch-pending');
    if (hero.hex) {
      // A fill attribute, not a style attribute: the deploy's CSP forbids
      // inline styles, and a presentation attribute is not one.
      svg.lastElementChild.setAttribute('fill', hero.hex);
      this._text(svg, 160, 126, hero.name, 'diagram-label');
    } else {
      this._text(svg, 160, 126, this.data.diagram.swatch_pending, 'diagram-small');
    }
    this._text(svg, 160, 22, this.data.diagram.bands_sum, 'diagram-small');
  }

  _finale(svg) {
    const hero = this.data.hero_planet;
    this._box(svg, 122, 30, 76, 60, hero.hex ? 'swatch' : 'swatch swatch-pending');
    if (hero.hex) svg.lastElementChild.setAttribute('fill', hero.hex);
    const caption = hero.hex ? hero.name : this.data.diagram.hero_pending;
    this._text(svg, 160, 112, caption, 'diagram-small');
  }
}
