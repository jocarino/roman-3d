// Panels, overlays and the exploded-view slider.
//
// Not one string in this file is user-visible copy. Everything rendered comes
// out of facts.json, which is the rule the content tests enforce: if a sentence
// is on the screen, it is in the data file with a source beside it.

const focusable =
  'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])';

export class UI {
  constructor({ facts, mission, root, observatory, controls }) {
    this.facts = facts;
    this.mission = mission;
    this.root = root;
    this.observatory = observatory;
    this.controls = controls;

    this.components = new Map(facts.components.map((c) => [c.id, c]));
    this.groupToComponents = new Map();
    for (const entry of observatory.model.header.components) {
      const list = this.groupToComponents.get(entry.group) || [];
      list.push(entry.id);
      this.groupToComponents.set(entry.group, list);
    }

    this.panel = root.querySelector('#panel');
    this.panelBody = root.querySelector('#panel-body');
    this.hoverLabel = root.querySelector('#hover-label');
    this.selected = -1;
    this.lastFocus = null;

    this._wireDialogs();
    this._wireViews();
    this._wireExplode();
    this._wireReset();
  }

  _wireDialogs() {
    wireOverlays(this.root, {
      onOpen: (dialog, opener) => this.openDialog(dialog, opener),
      onClose: (dialog) => this.closeDialog(dialog),
    });
    this.root.querySelector('#panel-close')?.addEventListener('click', () => this.clearSelection());
  }

  _wireViews() {
    this.root.querySelectorAll('[data-view]').forEach((button) => {
      button.addEventListener('click', () => {
        this.controls.snapTo(button.dataset.view);
        this._markActiveView(button.dataset.view);
      });
    });
  }

  _markActiveView(name) {
    this.root.querySelectorAll('[data-view]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.view === name));
    });
  }

  /** Called when the camera moves by any route other than a view button. */
  clearActiveView() {
    this._markActiveView(null);
  }

  _wireExplode() {
    const slider = this.root.querySelector('#explode-range');
    if (!slider) return;
    const apply = () => {
      const amount = Number(slider.value) / 100;
      this.observatory.setExplode(amount);
      slider.setAttribute('aria-valuetext', `${slider.value} percent apart`);
      // Drives the filled part of the track; the square look is all CSS.
      slider.style.setProperty('--fill', `${slider.value}%`);
    };
    slider.addEventListener('input', apply);
    this.applyExplode = apply;
    apply();
    this.explodeSlider = slider;
  }

  _wireReset() {
    this.resetButton = this.root.querySelector('#reset-view');
    this.resetButton?.addEventListener('click', () => this.resetView());
    this.resetEnabled = null;
    this.refreshReset();
  }

  /**
   * Enable Reset only once there is something to put back: a view chosen, the
   * model orbited or zoomed, the exploded view opened, or a part selected.
   * Called every frame, so it only touches the DOM when the answer changes.
   */
  refreshReset() {
    if (!this.resetButton) return;
    const moved = Boolean(this.controls?.interacted);
    const exploded = Number(this.explodeSlider?.value || 0) > 0;
    const can = moved || exploded || this.selected >= 0;
    if (can === this.resetEnabled) return;
    this.resetEnabled = can;
    this.resetButton.disabled = !can;
    this.resetButton.title = can
      ? this.facts.ui.reset_title
      : this.facts.ui.reset_idle_title;
  }

  /** Put everything back: camera, exploded view, selection, pressed states. */
  resetView() {
    // notify:false, because the callback below is what brought us here when the
    // reset came from a double click or the 0 key.
    this.controls?.reset({ notify: false });
    this.afterReset();
  }

  /** Everything a reset does except move the camera. */
  afterReset() {
    this.resetExplode();
    this.clearSelection();
    this._markActiveView(null);
  }

  resetExplode() {
    if (!this.explodeSlider) return;
    this.explodeSlider.value = '0';
    // Through apply(), so aria-valuetext and the track fill stay in step.
    this.applyExplode();
  }

  openDialog(dialog, opener) {
    this.lastFocus = opener || document.activeElement;
    dialog.hidden = false;
    dialog.setAttribute('aria-hidden', 'false');
    const first = dialog.querySelector(focusable);
    if (first) first.focus();
  }

  closeDialog(dialog) {
    dialog.hidden = true;
    dialog.setAttribute('aria-hidden', 'true');
    if (this.lastFocus) this.lastFocus.focus();
  }

  closeTopDialog() {
    const open = [...this.root.querySelectorAll('[role="dialog"]')].filter((d) => !d.hidden);
    const top = open[open.length - 1];
    if (!top) return false;
    // The component panel is a dialog too, but closing it has to release the
    // selection as well. Hiding it alone left `selected` set, which made
    // setHover() bail on every later move and killed hovering for the session.
    if (top === this.panel) {
      this.clearSelection();
      this.lastFocus?.focus?.();
      return true;
    }
    this.closeDialog(top);
    return true;
  }

  /** Hover feedback: brighten the group and float its name near the cursor. */
  setHover(groupIndex, x, y) {
    if (this.selected >= 0) return;
    this.observatory.setHighlight(groupIndex);
    if (groupIndex < 0) {
      this.hoverLabel.hidden = true;
      return;
    }
    const group = this.observatory.groups[groupIndex];
    const ids = this.groupToComponents.get(group.id) || [];
    const names = ids.map((id) => this.components.get(id)?.name).filter(Boolean);
    this.hoverLabel.textContent = names.length ? names.join(' and ') : group.label;
    this.hoverLabel.hidden = false;
    this.hoverLabel.style.left = `${x}px`;
    this.hoverLabel.style.top = `${y}px`;
  }

  select(groupIndex) {
    if (groupIndex < 0) {
      this.clearSelection();
      return;
    }
    this.selected = groupIndex;
    this.observatory.setHighlight(groupIndex);
    this.hoverLabel.hidden = true;

    const group = this.observatory.groups[groupIndex];
    const ids = this.groupToComponents.get(group.id) || [];
    this.panelBody.replaceChildren(...ids.map((id, i) => this._renderComponent(id, ids, i)));
    this.panel.hidden = false;
    this.panel.setAttribute('aria-hidden', 'false');
    // Shrink the stage rather than cover it: the ResizeObserver on #app-stage
    // reframes the camera, so the part you just clicked stays on screen.
    document.body.classList.add('panel-open');
    this.root.querySelector('#panel-close')?.focus();
  }

  clearSelection() {
    this.selected = -1;
    this.observatory.setHighlight(-1);
    this.panel.hidden = true;
    this.panel.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('panel-open');
  }

  _renderComponent(id, siblings, position) {
    const data = this.components.get(id);
    const article = el('article', 'component');
    if (!data) return article;

    article.append(el('h2', 'component-name', data.name));
    article.append(el('p', 'component-short', data.short));
    article.append(this._sourced(el('p', 'component-blurb', data.blurb.text), data.blurb.source));

    const list = el('ul', 'fact-list');
    for (const fact of data.facts) {
      const item = el('li', 'fact');
      item.append(document.createTextNode(fact.text));
      item.append(this._sourceLink(fact.source, fact.source_note));
      list.append(item);
    }
    article.append(list);

    if (siblings.length > 1 && position === siblings.length - 1) {
      const shared = this.facts.shared_geometry;
      article.append(this._sourced(el('p', 'shared-note', shared.text), shared.source));
    }

    const official = this.facts.sources[data.official];
    if (official) {
      const link = el('a', 'official-link', this.facts.ui.panel_official);
      link.href = official.url;
      link.rel = 'noopener';
      link.target = '_blank';
      article.append(link);
    }
    return article;
  }

  _sourced(node, sourceId) {
    node.append(this._sourceLink(sourceId));
    return node;
  }

  _sourceLink(sourceId, note) {
    const source = this.facts.sources[sourceId];
    const link = el('a', 'source-link', '?');
    link.href = source ? source.url : '#';
    link.rel = 'noopener';
    link.target = '_blank';
    link.setAttribute(
      'aria-label',
      note ? `Source: ${source?.label || sourceId}. ${note}` : `Source: ${source?.label || sourceId}`
    );
    link.title = note ? `${source?.label || sourceId}. ${note}` : source?.label || sourceId;
    return link;
  }
}

/**
 * Wire the about and info overlays.
 *
 * Split out of the UI class because the no-WebGL path has no renderer to build
 * a UI around, and the About overlay is where the not-affiliated disclaimer
 * lives. That has to work for everyone, 3D or not.
 */
export function wireOverlays(root, handlers = {}) {
  const open = handlers.onOpen || ((dialog) => show(dialog, true));
  const close = handlers.onClose || ((dialog) => show(dialog, false));
  for (const [openId, dialogId] of [
    ['about-open', 'about'],
    ['info-open', 'info'],
  ]) {
    const opener = root.querySelector(`#${openId}`);
    const dialog = root.querySelector(`#${dialogId}`);
    if (!opener || !dialog) continue;
    opener.addEventListener('click', () => open(dialog, opener));
    dialog.querySelectorAll('[data-close]').forEach((button) => {
      button.addEventListener('click', () => close(dialog));
    });
  }
}

function show(dialog, visible) {
  dialog.hidden = !visible;
  dialog.setAttribute('aria-hidden', String(!visible));
  if (visible) dialog.querySelector(focusable)?.focus();
}

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}
