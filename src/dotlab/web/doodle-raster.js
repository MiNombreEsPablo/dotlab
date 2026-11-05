// The doodle's drawing engine: pure functions on a bit grid (one byte per dot, 1 = ink), no DOM, so Node can test it.
// It is the web counterpart of the Qt app's DoodleCanvas: the same tools, hard-edged strokes (the printer is 1-bit),
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
  constructor({ width, height, inks, undoLimit = 30, random = Math.random }) {
    this.width = width;
    this.height = height;
    this.inks = Object.fromEntries(inks.map(([name, , rows]) => [name, rows]));
    this.undoLimit = undoLimit;
    this.random = random;
    this.tool = "pen";
    this.brush = 4;
    this.ink = "solid";
    this.sticker = null; // 24 rows of "0"/"1"
    this.stickerScale = 2;
    this.pixels = new Uint8Array(width * height);
    this.underlay = null; // 1 where the label itself is dark: the bucket stops there
    this._undo = [];
    this._start = null;
    this._last = null;
    this._now = null;
    this._hover = null;
  }

  // --- state -------------------------------------------------------------------------------------------------------

  isEmpty() { return !this.pixels.some((v) => v); }
  canUndo() { return this._undo.length > 0; }
  setMask(mask) { this.pixels = Uint8Array.from(mask); this._undo = []; this._start = null; }
  setUnderlay(dark) { this.underlay = dark; }

  _remember() {
    this._undo.push(this.pixels.slice());
    if (this._undo.length > this.undoLimit) this._undo.shift();
  }
  undo() {
    if (!this._undo.length) return false;
    this.pixels = this._undo.pop();
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

  _stampDots(centre) { // the sticker enlarged by whole numbers, centred on `centre`: [[x, y], ...]
    if (!this.sticker) return [];
    const s = this.stickerScale;
    const size = this.sticker.length * s;
    const left = centre[0] - (size >> 1);
    const top = centre[1] - (size >> 1);
    const dots = [];
    this.sticker.forEach((row, j) => {
      for (let i = 0; i < row.length; i++) {
        if (row[i] !== "1") continue;
        for (let dy = 0; dy < s; dy++) for (let dx = 0; dx < s; dx++) dots.push([left + i * s + dx, top + j * s + dy]);
      }
    });
    return dots;
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
    this._remember();
    if (this.tool === "fill") {
      if (this._bucket(at)) return true;
      this._undo.pop(); // nothing changed, so nothing to undo
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
    if (this.tool === "stamp") {
      for (const [px, py] of this._stampDots(end)) this._dot(this.pixels, px, py, 1, () => true);
    } else if (["line", "box", "oval"].includes(this.tool)) {
      this._shape(this.pixels, this._start, end);
    }
    this._start = this._last = this._now = null;
    return true;
  }

  leave() { this._hover = null; }
  cancel() { // a stroke that was interrupted: keep what was drawn, as the Qt canvas does when the button is released
    this._start = this._last = this._now = null;
  }

  // --- display -----------------------------------------------------------------------------------------------------

  // The ink as dots (black unless a look tints it) with alpha, plus what is being dragged out (a rubber-band shape) and the sticker's ghost.
  toRgba(out, ink = [0, 0, 0]) {
    let layer = this.pixels;
    let ghost = [];
    if (this.tool === "stamp" && (this._hover || this._start)) ghost = this._stampDots(this._start ? this._now : this._hover);
    else if (this._start && ["line", "box", "oval"].includes(this.tool)) {
      layer = this.pixels.slice();
      this._shape(layer, this._start, this._now);
    }
    for (let i = 0; i < layer.length; i++) {
      out[i * 4] = ink[0];
      out[i * 4 + 1] = ink[1];
      out[i * 4 + 2] = ink[2];
      out[i * 4 + 3] = layer[i] ? 255 : 0;
    }
    for (const [x, y] of ghost) {
      if (x < 0 || y < 0 || x >= this.width || y >= this.height) continue;
      const i = (y * this.width + x) * 4;
      if (!out[i + 3]) out[i + 3] = 128;
    }
    return out;
  }
}
