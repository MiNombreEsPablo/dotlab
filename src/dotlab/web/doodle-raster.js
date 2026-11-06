// The doodle's drawing engine: pure functions on a bit grid (one byte per dot, 1 = ink), no DOM, so Node can test it.
// The doodle's tools: hard-edged strokes (the printer is 1-bit),
// dither-pattern inks anchored to the label, a bucket that stops at ink and at the label's own dark pixels, and undo. What it paints is the doodle: doodle.py decodes it, the engine draws it over everything.
//
//   const d = new Doodle({ width, height, inks, undoLimit });   d.tool = "pen"; d.brush = 4; d.ink = "half";
//   d.down(x, y); d.move(x, y); d.up(x, y);   d.pixels   d.toRgba(out)

const SHAPES = ["line", "box", "oval", "fbox", "foval"]; // the tools that are dragged out and drawn on release
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
  constructor({ width, height, inks, undoLimit = 30, random = Math.random }) {
    this.width = width;
    this.height = height;
    this.inks = Object.fromEntries(inks.map(([name, , rows]) => [name, rows]));
    this.undoLimit = undoLimit;
    this.random = random;
    this.tool = "pen";
    this.brush = 4;
    this.ink = "solid";
    this.constrain = false; // Shift held: lines snap to 45 degrees, rectangles and ellipses become squares and circles
    this.grid = 8; // spacing of the snap grid, in dots
    this.showGrid = false;
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

  isEmpty() { return !this.pixels.some((v) => v); }
  canUndo() { return this._undo.length > 0; }
  canRedo() { return this._redo.length > 0; }
  setMask(mask) { this.pixels = Uint8Array.from(mask); this._undo = []; this._redo = []; this._start = null; }
  setUnderlay(dark) { this.underlay = dark; }

  _snap() { return { pixels: this.pixels.slice() }; }
  _restore(snap) { this.pixels = snap.pixels; }
  _push(snap) {
    this._redo = [];
    this._undo.push(snap);
    if (this._undo.length > this.undoLimit) this._undo.shift();
  }
  _remember() {
    this._push(this._snap());
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
  clear() {
    if (this.isEmpty()) return false;
    this._remember();
    this.pixels.fill(0);
    return true;
  }

  // --- painting ----------------------------------------------------------------------------------------------------

  _pattern() { // does the chosen ink put a dot here? Tiles are anchored to the label, so strokes line up.
    const rows = this.tool === "eraser" || !this.inks[this.ink] ? this.inks.solid : this.inks[this.ink];
    const n = rows.length; // 4 or 8: a square tile
    return (x, y) => rows[y % n][x % n] === "#";
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

  _constrained(a, b) { // the far corner of a shape, pulled to a 45-degree line or a square while Shift is held
    if (!this.constrain) return b;
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const ax = Math.abs(dx);
    const ay = Math.abs(dy);
    if (this.tool === "line") {
      if (ay * 2 < ax) return [b[0], a[1]]; // closer to horizontal
      if (ax * 2 < ay) return [a[0], b[1]]; // closer to vertical
    }
    const side = Math.max(ax, ay);
    return [a[0] + Math.sign(dx || 1) * side, a[1] + Math.sign(dy || 1) * side];
  }

  _shape(target, a, end) { // line, rectangle or ellipse (outlined with the brush, or filled with the ink), drawn with the brush
    const b = this._constrained(a, end);
    const allowed = this._pattern();
    const brush = (x, y) => this._disc(target, x, y, this.brush, 1, allowed);
    if (this.tool === "line") {
      for (const [x, y] of linePoints(a[0], a[1], b[0], b[1])) brush(x, y);
      return;
    }
    const [x0, x1] = [Math.min(a[0], b[0]), Math.max(a[0], b[0])];
    const [y0, y1] = [Math.min(a[1], b[1]), Math.max(a[1], b[1])];
    const filled = this.tool === "fbox" || this.tool === "foval";
    if (filled) { // the inside takes the ink's pattern, the outline is solid, as in Decker's "filled" shapes
      const oval = this.tool === "foval";
      const cx = (x0 + x1) / 2;
      const cy = (y0 + y1) / 2;
      const rx = (x1 - x0) / 2 + 0.5;
      const ry = (y1 - y0) / 2 + 0.5;
      for (let y = y0; y <= y1; y++) {
        for (let x = x0; x <= x1; x++) {
          if (oval && ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 > 1) continue;
          this._dot(target, x, y, 1, allowed);
        }
      }
      const solid = () => true;
      const outline = (x, y) => this._disc(target, x, y, this.brush, 1, solid);
      if (!oval) {
        for (const [p, q] of [[[x0, y0], [x1, y0]], [[x1, y0], [x1, y1]], [[x1, y1], [x0, y1]], [[x0, y1], [x0, y0]]]) {
          for (const [x, y] of linePoints(p[0], p[1], q[0], q[1])) outline(x, y);
        }
        return;
      }
      const steps = Math.max(16, Math.ceil(2 * Math.PI * Math.max(rx, ry)) * 2);
      for (let k = 0; k < steps; k++) {
        const t = (k / steps) * 2 * Math.PI;
        outline(Math.round(cx + (rx - 0.5) * Math.cos(t)), Math.round(cy + (ry - 0.5) * Math.sin(t)));
      }
      return;
    }
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
    const walls = dilate(this.pixels, width, height);
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

  down(x, y) {
    const at = [x, y];
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
    if (SHAPES.includes(this.tool)) {
      this._shape(this.pixels, this._start, end);
    }
    this._start = this._last = this._now = null;
    return true;
  }

  snap(x, y) { // a point pulled to the nearest grid crossing (when the snap grid is on, see showGrid)
    const g = this.grid;
    return [Math.min(this.width - 1, Math.round(x / g) * g), Math.min(this.height - 1, Math.round(y / g) * g)];
  }
  leave() { this._hover = null; }
  cancel() { // a stroke that was interrupted: keep what was drawn, as when the button is released
    this._start = this._last = this._now = null;
  }

  // --- display -----------------------------------------------------------------------------------------------------

  // The ink as dots (black unless a look tints it) with alpha, plus what is being dragged out (a rubber-band shape).
  toRgba(out, ink = [0, 0, 0]) {
    let layer = this.pixels;
    const ghost = [];
    if (this._start && SHAPES.includes(this.tool)) {
      layer = this.pixels.slice();
      this._shape(layer, this._start, this._now);
    }
    if (this.showGrid) { // graph-paper crosses where the snap grid's lines meet (faint, and only on bare label)
      for (let y = 0; y < this.height; y += this.grid) for (let x = 0; x < this.width; x += this.grid) ghost.push([x, y, 70]);
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
