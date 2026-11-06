// The doodle's drawing engine: pure functions on a bit grid (one byte per dot, 1 = ink), no DOM, so Node can test it.
// The doodle's tools: hard-edged strokes (the printer is 1-bit),
// dither-pattern inks anchored to the label, a bucket that stops at ink and at the label's own dark pixels, stickers as
// stamps, and undo. What it paints is the doodle: doodle.py decodes it, the engine draws it over everything.
//
//   const d = new Doodle({ width, height, inks, undoLimit });   d.tool = "pen"; d.brush = 4; d.ink = "half";
//   d.down(x, y); d.move(x, y); d.up(x, y);   d.pixels   d.toRgba(out)

const circle = new Map(); // diameter -> [[dx, dy], ...] covering a round brush

function discOffsets(d) {
  if (!circle.has(d)) {
    const cells = [];
    for (let j = 0; j < d; j++) {
      for (let i = 0; i < d; i++) {
        const dx = i + 0.5 - d / 2;
        const dy = j + 0.5 - d / 2;
        if (dx * dx + dy * dy <= (d / 2) * (d / 2)) cells.push([i, j]);
      }
    }
    circle.set(d, cells);
  }
  return circle.get(d);
}

// Every dot on the straight line a -> b, both ends included (Bresenham).
function linePoints(x0, y0, x1, y1) {
  const points = [];
  const dx = Math.abs(x1 - x0);
  const dy = -Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1;
  const sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  for (let x = x0, y = y0; ; ) {
    points.push([x, y]);
    if (x === x1 && y === y1) break;
    const e2 = 2 * err;
    if (e2 >= dy) { err += dy; x += sx; }
    if (e2 <= dx) { err += dx; y += sy; }
  }
  return points;
}

function dilate(src, width, height) { // each dot becomes the strongest of its 3x3 neighbourhood
  const across = new Uint8Array(src.length);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      across[i] = src[i] | (x > 0 ? src[i - 1] : 0) | (x < width - 1 ? src[i + 1] : 0);
    }
  }
  const out = new Uint8Array(src.length);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      out[i] = across[i] | (y > 0 ? across[i - width] : 0) | (y < height - 1 ? across[i + width] : 0);
    }
  }
  return out;
}

export class Doodle {
  constructor({ width, height, inks, undoLimit = 30, random = Math.random, designs = {}, scaleLimits = [1, 9], maxStickers = 40 }) {
    this.width = width;
    this.height = height;
    this.inks = Object.fromEntries(inks.map(([name, , rows]) => [name, rows]));
    this.undoLimit = undoLimit;
    this.random = random;
    this.tool = "pen";
    this.brush = 4;
    this.ink = "solid";
    // Stickers are objects, not ink: placed ones can be selected, moved, resized and removed. `designs` maps a name to its
    // 24 rows of "0"/"1"; a placed sticker is {name, x, y, scale} with (x, y) its centre, drawn under the ink.
    this.designs = designs;
    this.stickerName = Object.keys(designs)[0] || null; // what the next click places
    this.stickerScale = 2; // and how large
    this.scaleLimits = scaleLimits;
    this.maxStickers = maxStickers;
    this.stickers = [];
    this.selected = -1;
    this._drag = null;
    this._key = null; // the last coalesced edit (a slider drag or a run of arrow keys is one undo step)
    this.pixels = new Uint8Array(width * height);
    this.underlay = null; // 1 where the label itself is dark: the bucket stops there
    this._undo = [];
    this._redo = [];
    this._start = null;
    this._last = null;
    this._now = null;
    this._hover = null;
  }

  // --- state -------------------------------------------------------------------------------------------------------

  isEmpty() { return !this.stickers.length && !this.pixels.some((v) => v); }
  canUndo() { return this._undo.length > 0; }
  canRedo() { return this._redo.length > 0; }
  setMask(mask) { this.pixels = Uint8Array.from(mask); this._undo = []; this._redo = []; this._start = null; }
  setStickers(list) { // [{name, x, y, scale}, ...] from a stored label: anything unknown is dropped
    const [lo, hi] = this.scaleLimits;
    this.stickers = list.filter((s) => this.designs[s.name]).slice(0, this.maxStickers)
      .map((s) => ({ name: s.name, x: Math.round(s.x), y: Math.round(s.y), scale: Math.min(hi, Math.max(lo, Math.round(s.scale))) }));
    this.selected = -1;
    this._drag = null;
    this._undo = [];
    this._redo = [];
  }
  setUnderlay(dark) { this.underlay = dark; }

  _snap() { return { pixels: this.pixels.slice(), stickers: this.stickers.map((s) => ({ ...s })), selected: this.selected }; }
  _restore(snap) { this.pixels = snap.pixels; this.stickers = snap.stickers; this.selected = snap.selected; this._drag = null; this._key = null; }
  _push(snap) {
    this._redo = [];
    this._undo.push(snap);
    if (this._undo.length > this.undoLimit) this._undo.shift();
  }
  _remember() {
    this._push(this._snap());
    this._key = null;
  }
  undo() {
    if (!this._undo.length) return false;
    this._redo.push(this._snap());
    this._restore(this._undo.pop());
    return true;
  }
  redo() {
    if (!this._redo.length) return false;
    this._undo.push(this._snap());
    this._restore(this._redo.pop());
    return true;
  }
  clear() { // the ink and the stickers
    if (this.isEmpty()) return false;
    this._remember();
    this.pixels.fill(0);
    this.stickers = [];
    this.selected = -1;
    return true;
  }

  // --- stickers ----------------------------------------------------------------------------------------------------

  _box(s) { // [left, top, right, bottom): the sticker's square, enlarged by whole numbers around its centre
    const size = this.designs[s.name].length * s.scale;
    const left = s.x - (size >> 1);
    const top = s.y - (size >> 1);
    return [left, top, left + size, top + size];
  }
  _forDots(name, scale, centre, put) { // calls put(x, y) for each dot of a design enlarged `scale` times, centred on `centre`
    const rows = this.designs[name];
    const [left, top] = this._box({ name, scale, x: centre[0], y: centre[1] });
    rows.forEach((row, j) => {
      for (let i = 0; i < row.length; i++) {
        if (row[i] !== "1") continue;
        for (let dy = 0; dy < scale; dy++) for (let dx = 0; dx < scale; dx++) put(left + i * scale + dx, top + j * scale + dy);
      }
    });
  }
  hit(x, y) { // the topmost placed sticker whose square holds this dot, or -1
    for (let i = this.stickers.length - 1; i >= 0; i--) {
      const [x0, y0, x1, y1] = this._box(this.stickers[i]);
      if (x >= x0 && x < x1 && y >= y0 && y < y1) return i;
    }
    return -1;
  }
  selectedSticker() { return this.selected >= 0 ? this.stickers[this.selected] : null; }
  deselect() { this.selected = -1; }
  _clampCentre(v, limit) { return Math.min(limit - 1, Math.max(0, v)); }
  _edit(key, change) { // one undo step per run of the same kind of edit on the same sticker
    const sticker = this.selectedSticker();
    if (!sticker) return false;
    const before = this._snap();
    if (!change(sticker)) return false;
    if (this._key !== key) { this._push(before); this._key = key; }
    return true;
  }
  resizeSelected(scale) {
    const [lo, hi] = this.scaleLimits;
    const to = Math.min(hi, Math.max(lo, Math.round(scale)));
    return this._edit(`scale:${this.selected}`, (s) => s.scale !== to && ((s.scale = to), true));
  }
  nudgeSelected(dx, dy) {
    return this._edit(`nudge:${this.selected}`, (s) => {
      const x = this._clampCentre(s.x + dx, this.width);
      const y = this._clampCentre(s.y + dy, this.height);
      if (x === s.x && y === s.y) return false;
      s.x = x;
      s.y = y;
      return true;
    });
  }
  deleteSelected() {
    if (!this.selectedSticker()) return false;
    this._remember();
    this.stickers.splice(this.selected, 1);
    this.selected = -1;
    return true;
  }
  _stickerLayer() { // the ink plus every placed sticker, as one mask (a copy)
    const layer = this.pixels.slice();
    for (const s of this.stickers) {
      this._forDots(s.name, s.scale, [s.x, s.y], (x, y) => {
        if (x >= 0 && y >= 0 && x < this.width && y < this.height) layer[y * this.width + x] = 1;
      });
    }
    return layer;
  }

  // --- painting ----------------------------------------------------------------------------------------------------

  _pattern() { // does the chosen ink put a dot here? Tiles are anchored to the label, so strokes line up.
    const rows = this.tool === "eraser" || !this.inks[this.ink] ? this.inks.solid : this.inks[this.ink];
    return (x, y) => rows[y & 3][x & 3] === "#";
  }

  _dot(target, x, y, value, allowed) {
    if (x < 0 || y < 0 || x >= this.width || y >= this.height) return;
    if (value === 0 || allowed(x, y)) target[y * this.width + x] = value;
  }

  _disc(target, cx, cy, diameter, value, allowed) {
    const left = cx - (diameter >> 1);
    const top = cy - (diameter >> 1);
    for (const [i, j] of discOffsets(diameter)) this._dot(target, left + i, top + j, value, allowed);
  }

  _square(target, x, y, size, allowed) {
    for (let j = 0; j < size; j++) for (let i = 0; i < size; i++) this._dot(target, x + i, y + j, 1, allowed);
  }

  _freehand(target, a, b) { // one stretch of a freehand tool, a -> b (equal for a click)
    const allowed = this._pattern();
    if (this.tool === "pen" || this.tool === "eraser") {
      const eraser = this.tool === "eraser";
      for (const [x, y] of linePoints(a[0], a[1], b[0], b[1])) {
        this._disc(target, x, y, eraser ? this.brush * 2 : this.brush, eraser ? 0 : 1, allowed);
      }
    } else if (this.tool === "spray") {
      this._sprayAt(target, b);
    } else {
      const half = this.brush >> 1;
      const steps = Math.max(Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1]), 1);
      for (let i = 0; i <= steps; i++) { // a dab at every dot along the way, so a fast stroke stays unbroken
        const x = a[0] + Math.floor(((b[0] - a[0]) * i) / steps);
        const y = a[1] + Math.floor(((b[1] - a[1]) * i) / steps);
        if (this.tool === "square") this._square(target, x - half, y - half, this.brush, allowed);
        else { // calligraphy: a slanted nib two dots thick
          for (const [px, py] of linePoints(x - half, y + half, x + half, y - half)) this._square(target, px, py, 2, allowed);
        }
      }
    }
  }

  _sprayAt(target, centre) {
    const radius = this.brush * 2;
    const solid = () => true;
    for (let n = Math.max(3, Math.floor((radius * radius) / 10)); n > 0; n--) {
      const r = radius * Math.sqrt(this.random());
      const angle = this.random() * 6.2832;
      this._dot(target, centre[0] + Math.round(r * Math.cos(angle)), centre[1] + Math.round(r * Math.sin(angle)), 1, solid);
    }
  }

  _shape(target, a, b) { // line, rectangle or ellipse, drawn with the brush
    const allowed = this._pattern();
    const brush = (x, y) => this._disc(target, x, y, this.brush, 1, allowed);
    if (this.tool === "line") {
      for (const [x, y] of linePoints(a[0], a[1], b[0], b[1])) brush(x, y);
      return;
    }
    const [x0, x1] = [Math.min(a[0], b[0]), Math.max(a[0], b[0])];
    const [y0, y1] = [Math.min(a[1], b[1]), Math.max(a[1], b[1])];
    if (this.tool === "box") {
      for (const [p, q] of [[[x0, y0], [x1, y0]], [[x1, y0], [x1, y1]], [[x1, y1], [x0, y1]], [[x0, y1], [x0, y0]]]) {
        for (const [x, y] of linePoints(p[0], p[1], q[0], q[1])) brush(x, y);
      }
      return;
    }
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    const rx = (x1 - x0) / 2;
    const ry = (y1 - y0) / 2;
    const steps = Math.max(16, Math.ceil(2 * Math.PI * Math.max(rx, ry)) * 2); // dense enough to leave no gaps
    for (let k = 0; k < steps; k++) {
      const t = (k / steps) * 2 * Math.PI;
      brush(Math.round(cx + rx * Math.cos(t)), Math.round(cy + ry * Math.sin(t)));
    }
  }

  // The paint bucket: fill the enclosed area around `at`, stopped by ink and by the label's own dark pixels. Patterned
  // lines have gaps, so the walls are thickened to flood against and the filled area is grown back to meet them.
  _bucket(at) {
    const { width, height } = this;
    const walls = dilate(this.stickers.length ? this._stickerLayer() : this.pixels, width, height);
    if (this.underlay) for (let i = 0; i < walls.length; i++) walls[i] |= this.underlay[i];
    if (walls[at[1] * width + at[0]]) return false; // clicked on a line
    const region = new Uint8Array(walls.length);
    const stack = [at[0] + at[1] * width];
    region[stack[0]] = 1;
    while (stack.length) {
      const i = stack.pop();
      const x = i % width;
      for (const j of [x > 0 ? i - 1 : -1, x < width - 1 ? i + 1 : -1, i - width, i + width]) {
        if (j >= 0 && j < walls.length && !walls[j] && !region[j]) { region[j] = 1; stack.push(j); }
      }
    }
    const grown = dilate(region, width, height);
    const allowed = this._pattern();
    for (let i = 0; i < grown.length; i++) if (grown[i] && allowed(i % width, Math.floor(i / width))) this.pixels[i] = 1;
    return true;
  }

  // --- pointer -----------------------------------------------------------------------------------------------------
  // Positions are dots [x, y]. down() and up() return true when the doodle changed.

  _stampDown(x, y) { // click a placed sticker to select it (and drag it); click empty label to place a new one
    const before = this._snap();
    const i = this.hit(x, y);
    this._start = this._now = [x, y];
    if (i >= 0) {
      this.selected = i;
      this._drag = { dx: this.stickers[i].x - x, dy: this.stickers[i].y - y, before, committed: false };
      return false;
    }
    if (!this.stickerName || this.stickers.length >= this.maxStickers) {
      this.selected = -1;
      this._drag = null;
      return false;
    }
    this._push(before); // placed: a step of its own; dragging before the button is released only positions it
    this._key = null;
    this.stickers.push({ name: this.stickerName, x, y, scale: this.stickerScale });
    this.selected = this.stickers.length - 1;
    this._drag = { dx: 0, dy: 0, before, committed: true };
    return true;
  }

  down(x, y) {
    const at = [x, y];
    if (this.tool === "stamp") return this._stampDown(x, y);
    this.selected = -1;
    const redo = this._redo;
    this._remember();
    if (this.tool === "fill") {
      if (this._bucket(at)) return true;
      this._undo.pop(); // nothing changed, so nothing to undo
      this._redo = redo;
      return false;
    }
    this._start = this._last = this._now = at;
    if (["pen", "square", "italic", "spray", "eraser"].includes(this.tool)) this._freehand(this.pixels, at, at);
    return false;
  }

  move(x, y) {
    this._hover = [x, y];
    if (!this._start) return;
    this._now = this._hover;
    if (this._drag) { // moving a sticker
      const s = this.selectedSticker();
      const x = this._clampCentre(this._now[0] + this._drag.dx, this.width);
      const y = this._clampCentre(this._now[1] + this._drag.dy, this.height);
      if (s && (x !== s.x || y !== s.y)) {
        if (!this._drag.committed) { this._push(this._drag.before); this._key = null; this._drag.committed = true; }
        s.x = x;
        s.y = y;
      }
      return;
    }
    if (["pen", "square", "italic", "eraser"].includes(this.tool)) this._freehand(this.pixels, this._last, this._now);
    this._last = this._now;
  }

  sprayTick() { // called on a timer while the spray can is held
    if (!this._start || this.tool !== "spray") return false;
    this._sprayAt(this.pixels, this._now);
    return true;
  }

  up(x, y) {
    if (!this._start) return false;
    const end = [x, y];
    if (this.tool === "stamp") {
      this.move(x, y); // the release is part of the drag
      const changed = !!this._drag && this._drag.committed;
      this._drag = null;
      this._start = this._last = this._now = null;
      return changed;
    }
    if (["line", "box", "oval"].includes(this.tool)) {
      this._shape(this.pixels, this._start, end);
    }
    this._start = this._last = this._now = null;
    return true;
  }

  leave() { this._hover = null; }
  cancel() { // a stroke that was interrupted: keep what was drawn, as when the button is released
    this._drag = null;
    this._start = this._last = this._now = null;
  }

  // --- display -----------------------------------------------------------------------------------------------------

  // The ink as dots (black unless a look tints it) with alpha, plus what is being dragged out (a rubber-band shape) and the sticker's ghost.
  toRgba(out, ink = [0, 0, 0]) {
    let layer = this.stickers.length ? this._stickerLayer() : this.pixels;
    const ghost = [];
    const stamping = this.tool === "stamp";
    if (stamping && this.stickerName && this._hover && !this._start && this.hit(...this._hover) < 0 && this.stickers.length < this.maxStickers) {
      this._forDots(this.stickerName, this.stickerScale, this._hover, (x, y) => ghost.push([x, y])); // where a click would place one
    } else if (this._start && ["line", "box", "oval"].includes(this.tool)) {
      if (layer === this.pixels) layer = this.pixels.slice();
      this._shape(layer, this._start, this._now);
    }
    if (stamping && this.selected >= 0) { // a dotted frame round the selected sticker
      const [x0, y0, x1, y1] = this._box(this.stickers[this.selected]).map((v, k) => (k < 2 ? v - 2 : v + 1));
      for (let x = x0; x <= x1; x++) for (const y of [y0, y1]) if ((x + y) % 2 === 0) ghost.push([x, y, 255]);
      for (let y = y0; y <= y1; y++) for (const x of [x0, x1]) if ((x + y) % 2 === 0) ghost.push([x, y, 255]);
    }
    for (let i = 0; i < layer.length; i++) {
      out[i * 4] = ink[0];
      out[i * 4 + 1] = ink[1];
      out[i * 4 + 2] = ink[2];
      out[i * 4 + 3] = layer[i] ? 255 : 0;
    }
    for (const [x, y, alpha = 128] of ghost) {
      if (x < 0 || y < 0 || x >= this.width || y >= this.height) continue;
      const i = (y * this.width + x) * 4;
      if (!out[i + 3]) out[i + 3] = alpha;
    }
    return out;
  }
}
