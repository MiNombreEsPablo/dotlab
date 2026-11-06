import test from "node:test";
import assert from "node:assert/strict";
import { Doodle } from "../doodle-raster.js";

const W = 384;
const H = 224;
const INKS = [
  ["solid", "Solid", ["####", "####", "####", "####"]],
  ["half", "50 % checker", ["#.#.", ".#.#", "#.#.", ".#.#"]],
  ["quarter", "25 % dots", ["#.#.", "....", "#.#.", "...."]],
  ["lines", "Lines", ["####", "....", "####", "...."]],
];
const make = (extra = {}) => new Doodle({ width: W, height: H, inks: INKS, ...extra });
const at = (d, x, y) => d.pixels[y * W + x];
const count = (d) => d.pixels.reduce((a, v) => a + v, 0);
const stroke = (d, tool, points) => {
  d.tool = tool;
  d.down(...points[0]);
  for (const p of points.slice(1)) d.move(...p);
  return d.up(...points[points.length - 1]);
};

test("a round brush is a disc: 1, 2 and 3 dots wide are 1, 4 and 9 dots", () => {
  for (const [brush, dots] of [[1, 1], [2, 4], [3, 9]]) {
    const d = make();
    d.brush = brush;
    stroke(d, "pen", [[50, 50]]);
    assert.equal(count(d), dots, `brush ${brush}`);
  }
});

test("a stroke has no gaps, however fast the pointer moved", () => {
  const d = make();
  d.brush = 1;
  stroke(d, "pen", [[10, 10], [200, 90]]); // one huge jump
  for (let x = 10; x <= 200; x++) {
    let found = false;
    for (let y = 0; y < H; y++) found = found || at(d, x, y) === 1;
    assert.ok(found, `column ${x} is empty`);
  }
});

test("the eraser is twice the brush wide and ignores the ink pattern", () => {
  const d = make();
  d.brush = 3;
  d.ink = "quarter"; // a sparse pattern would leave holes if the eraser respected it
  d.pixels.fill(1);
  stroke(d, "eraser", [[100, 100]]);
  assert.equal(W * H - count(d), 32); // a round brush 6 dots wide: a disc of 32 dots, none of them skipped
  assert.equal(at(d, 100, 100) + at(d, 97, 100) + at(d, 102, 100) + at(d, 100, 97) + at(d, 100, 102), 0); // centre and edges
  assert.equal(at(d, 97, 97) + at(d, 102, 102), 2); // the corners of a disc are not part of it
  assert.equal(at(d, 94, 100), 1); // and nothing wider
});

test("an ink pattern is anchored to the label, so neighbouring strokes line up", () => {
  const d = make();
  d.ink = "half";
  d.brush = 6;
  stroke(d, "square", [[40, 40]]);
  stroke(d, "square", [[43, 40]]); // overlaps the first
  for (let y = 38; y < 44; y++) for (let x = 38; x < 49; x++) if (at(d, x, y)) assert.equal((x + y) % 2, 0, `${x},${y}`);
  assert.ok(count(d) > 20);
});

test("a line, a rectangle and an ellipse are drawn on release; dragging only shows a preview", () => {
  const d = make();
  d.brush = 2;
  d.tool = "box";
  d.down(20, 20);
  d.move(80, 60);
  assert.equal(count(d), 0, "nothing is drawn while dragging");
  const rgba = d.toRgba(new Uint8ClampedArray(W * H * 4));
  assert.ok(rgba.some((v, i) => i % 4 === 3 && v === 255), "but the preview shows it");
  assert.equal(d.up(80, 60), true);
  assert.equal(at(d, 20, 40), 1); // left edge
  assert.equal(at(d, 80, 40), 1); // right edge
  assert.equal(at(d, 50, 20), 1); // top edge
  assert.equal(at(d, 50, 40), 0); // the inside is empty
});

test("an ellipse is closed, symmetric and stays inside its box (plus the brush)", () => {
  const d = make();
  d.brush = 1;
  stroke(d, "oval", [[100, 50], [180, 110]]);
  const xs = [];
  const ys = [];
  d.pixels.forEach((v, i) => { if (v) { xs.push(i % W); ys.push(Math.floor(i / W)); } });
  assert.deepEqual([Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)], [100, 180, 50, 110]);
  assert.equal(at(d, 140, 50) + at(d, 140, 110), 2); // top and bottom meet the box
  assert.equal(at(d, 140, 80), 0); // hollow
});

test("the paint bucket fills inside a closed shape only, and stops at its walls", () => {
  const d = make();
  d.brush = 2;
  stroke(d, "box", [[20, 20], [100, 80]]);
  const before = count(d);
  d.tool = "fill";
  assert.equal(d.down(60, 50), true);
  assert.equal(at(d, 60, 50), 1);
  assert.equal(at(d, 30, 30), 1);
  assert.equal(at(d, 10, 10), 0); // outside is untouched
  assert.equal(at(d, 200, 150), 0);
  assert.ok(count(d) > before + 3000);
});

test("the bucket stops at the label's own dark pixels, and does nothing when clicked on a line", () => {
  const d = make();
  const dark = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) dark[y * W + 150] = 1; // a vertical wall that is part of the label, not the doodle
  d.setUnderlay(dark);
  d.tool = "fill";
  assert.equal(d.down(50, 50), true);
  assert.equal(at(d, 100, 100), 1);
  assert.equal(at(d, 160, 100), 0, "the far side of the wall stays clear");
  const d2 = make();
  d2.setUnderlay(dark);
  d2.tool = "fill";
  assert.equal(d2.down(150, 100), false, "a click on a wall paints nothing");
  assert.equal(d2.canUndo(), false, "and leaves nothing to undo");
});

test("a patterned bucket fill keeps the pattern", () => {
  const d = make();
  d.brush = 2;
  stroke(d, "box", [[20, 20], [100, 80]]);
  d.ink = "quarter";
  d.tool = "fill";
  d.down(60, 50);
  for (let y = 30; y < 70; y++) for (let x = 30; x < 90; x++) assert.equal(at(d, x, y), (x & 1) === 0 && (y & 1) === 0 ? 1 : 0);
});

test("spray puts a handful of dots inside its radius, always solid", () => {
  let seed = 7;
  const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const d = make({ random });
  d.brush = 4; // radius 8, so max(3, 64 // 10) = 6 dots per spray
  d.ink = "quarter"; // spray ignores the pattern
  d.tool = "spray";
  d.down(100, 100);
  d.sprayTick();
  d.sprayTick();
  d.up(100, 100);
  assert.ok(count(d) > 6 && count(d) <= 18, `${count(d)} dots`);
  d.pixels.forEach((v, i) => {
    if (v) assert.ok(Math.hypot((i % W) - 100, Math.floor(i / W) - 100) <= 8.6);
  });
});

test("undo goes back stroke by stroke, 30 deep, and clear can be undone", () => {
  const d = make();
  d.brush = 1;
  for (let i = 0; i < 35; i++) stroke(d, "pen", [[10 + i * 3, 10]]);
  assert.equal(count(d), 35);
  let undone = 0;
  while (d.undo()) undone++;
  assert.equal(undone, 30);
  assert.equal(count(d), 5, "the five oldest strokes cannot be undone");
  assert.equal(d.clear(), true);
  assert.equal(count(d), 0);
  assert.equal(d.undo(), true);
  assert.equal(count(d), 5);
  assert.equal(make().clear(), false, "clearing nothing is not a change");
});

test("redo replays undone strokes, and a new stroke drops the redo history", () => {
  const d = make();
  d.brush = 1;
  for (let i = 0; i < 3; i++) stroke(d, "pen", [[10 + i * 3, 10]]);
  assert.equal(d.canRedo(), false);
  d.undo(); d.undo();
  assert.equal(count(d), 1);
  assert.equal(d.redo(), true);
  assert.equal(count(d), 2);
  assert.equal(d.redo(), true);
  assert.equal(count(d), 3);
  assert.equal(d.redo(), false);
  d.undo();
  stroke(d, "pen", [[50, 50]]);
  assert.equal(d.canRedo(), false, "drawing again forgets what was undone");
});

test("drawing at and past the edges never throws and stays on the label", () => {
  const d = make();
  d.brush = 24;
  for (const tool of ["pen", "square", "italic", "spray", "eraser"]) stroke(d, tool, [[0, 0], [W - 1, H - 1], [W - 1, 0]]);
  for (const tool of ["line", "box", "oval"]) stroke(d, tool, [[0, 0], [W - 1, H - 1]]);
  d.toRgba(new Uint8ClampedArray(W * H * 4));
  assert.equal(d.pixels.length, W * H);
});

test("a mask round-trips and starts a fresh undo history", () => {
  const d = make();
  const mask = new Uint8Array(W * H);
  mask[5 * W + 5] = 1;
  d.setMask(mask);
  assert.equal(d.isEmpty(), false);
  assert.equal(d.canUndo(), false);
  assert.deepEqual([...d.pixels], [...mask]);
  d.setMask(mask);
  d.pixels[0] = 1; // the doodle owns its copy
  assert.equal(mask[0], 0);
});

// --- filled shapes, Shift, the snap grid, 8x8 patterns -----------------------------------------------------------

test("a filled rectangle is full of the ink's pattern inside a solid outline", () => {
  const d = make();
  d.brush = 1;
  d.ink = "half";
  stroke(d, "fbox", [[20, 20], [39, 39]]);
  assert.equal(at(d, 20, 30), 1); // outline is solid even where the checker would be empty
  assert.equal(at(d, 22, 31) + at(d, 23, 31), 1); // inside: a 50 % checker, one of any two neighbours
  let inside = 0;
  for (let y = 21; y < 39; y++) for (let x = 21; x < 39; x++) inside += at(d, x, y);
  assert.equal(inside, 18 * 18 / 2);
  assert.equal(at(d, 40, 30), 0);
});

test("a filled ellipse stays inside its box and leaves the corners empty", () => {
  const d = make();
  d.brush = 1;
  d.ink = "solid";
  stroke(d, "foval", [[100, 100], [140, 120]]);
  assert.equal(at(d, 120, 110), 1);
  assert.equal(at(d, 101, 101), 0);
  assert.equal(at(d, 139, 119), 0);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (at(d, x, y)) assert.ok(x >= 100 && x <= 140 && y >= 99 && y <= 121, `${x},${y}`);
});

test("Shift pulls a line to 0, 45 or 90 degrees and a rectangle or ellipse to a square or circle", () => {
  const d = make();
  d.brush = 1;
  d.constrain = true;
  stroke(d, "line", [[50, 50], [100, 58]]); // nearly horizontal
  for (let x = 50; x <= 100; x++) assert.equal(at(d, x, 50), 1, `x ${x}`);
  const e = make();
  e.brush = 1;
  e.constrain = true;
  stroke(e, "line", [[50, 50], [90, 80]]); // closer to the diagonal
  assert.equal(at(e, 90, 90), 1);
  const f = make();
  f.brush = 1;
  f.constrain = true;
  stroke(f, "box", [[10, 10], [60, 30]]);
  assert.equal(at(f, 60, 60), 1); // square: the far corner is at 60,60
  assert.equal(at(f, 60, 30), 1);
  const g = make();
  g.constrain = true;
  g.tool = "line";
  g.down(10, 10);
  g.move(30, 14);
  const out = g.toRgba(new Uint8ClampedArray(W * H * 4));
  assert.equal(out[(10 * W + 30) * 4 + 3], 255); // the rubber band shows the constrained line too
});

test("the snap grid shows faint crosses on bare label only, and snap lands on grid crossings", () => {
  const d = make();
  d.showGrid = true;
  const out = d.toRgba(new Uint8ClampedArray(W * H * 4));
  assert.ok(out[(16 * W + 24) * 4 + 3] > 0 && out[(16 * W + 24) * 4 + 3] < 255);
  assert.equal(out[(17 * W + 24) * 4 + 3], 0);
  assert.deepEqual(d.snap(13, 21), [16, 24]);
  assert.deepEqual(d.snap(383, 223), [383, 223]); // never off the label
  d.showGrid = false;
  assert.equal(d.toRgba(new Uint8ClampedArray(W * H * 4))[(16 * W + 24) * 4 + 3], 0);
});

test("8x8 pattern tiles repeat every 8 dots, anchored to the label", () => {
  const rows = ["#.......", "........", "........", "........", "........", "........", "........", "........"];
  const d = make({ inks: [...INKS, ["dot8", "one in 64", rows]] });
  d.ink = "dot8";
  d.brush = 1;
  stroke(d, "fbox", [[0, 0], [30, 30]]);
  let inside = 0;
  for (let y = 1; y < 30; y++) for (let x = 1; x < 30; x++) inside += at(d, x, y);
  assert.equal(inside, 9); // dots at 8, 16, 24 in each direction
  assert.equal(at(d, 8, 8) + at(d, 16, 24), 2);
});

test("white ink paints 2, the bucket fills with the chosen colour, and a black stroke over it wins", () => {
  const d = make();
  d.brush = 1;
  d.color = 2;
  stroke(d, "pen", [[10, 10]]);
  assert.equal(at(d, 10, 10), 2);
  d.color = 1;
  stroke(d, "pen", [[10, 10]]);
  assert.equal(at(d, 10, 10), 1);
  const out = d.toRgba(new Uint8ClampedArray(W * H * 4), [0, 0, 0], [250, 250, 250]);
  stroke(d, "pen", [[20, 20]]);
  d.color = 2;
  stroke(d, "pen", [[30, 30]]);
  const rgba = d.toRgba(out, [0, 0, 0], [250, 250, 250]);
  assert.deepEqual([...rgba.slice((30 * W + 30) * 4, (30 * W + 30) * 4 + 4)], [250, 250, 250, 255]);
});
