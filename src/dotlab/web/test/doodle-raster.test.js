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

const THREE = ["11", "10"].concat(Array(22).fill("00")).map((row) => row.padEnd(24, "0")); // 24 rows, three dots set
const FULL = Array(24).fill("1".repeat(24));
const withStickers = (extra = {}) => make({ designs: { three: THREE, full: FULL }, ...extra });
const rgbaOf = (d) => d.toRgba(new Uint8ClampedArray(W * H * 4));
const alpha = (rgba, x, y) => rgba[(y * W + x) * 4 + 3];

test("a placed sticker is an object, enlarged by whole numbers around where it is released, not ink", () => {
  const d = withStickers();
  d.stickerName = "three";
  d.stickerScale = 2;
  assert.equal(stroke(d, "stamp", [[100, 100]]), true);
  assert.deepEqual(d.stickers, [{ name: "three", x: 100, y: 100, scale: 2 }]);
  assert.equal(count(d), 0, "the ink is untouched");
  const rgba = rgbaOf(d);
  const left = 100 - ((24 * 2) >> 1);
  const top = left;
  assert.equal(alpha(rgba, left, top), 255);
  assert.equal(alpha(rgba, left + 3, top + 1), 255);
  assert.equal(alpha(rgba, left + 3, top + 3), 0); // the sticker's own empty dot
});

test("dragging while the button is down positions the new sticker: one undo removes it", () => {
  const d = withStickers();
  d.stickerName = "full";
  stroke(d, "stamp", [[50, 50], [60, 70], [80, 90]]);
  assert.deepEqual(d.stickers.map((s) => [s.x, s.y]), [[80, 90]]);
  assert.equal(d.undo(), true);
  assert.equal(d.stickers.length, 0);
  assert.equal(d.redo(), true);
  assert.equal(d.stickers.length, 1);
});

test("clicking a placed sticker selects it and dragging moves it, keeping the grab offset", () => {
  const d = withStickers();
  d.stickerName = "full";
  d.stickerScale = 2; // 48 dots square
  stroke(d, "stamp", [[100, 100]]);
  stroke(d, "stamp", [[200, 100]]);
  assert.equal(d.stickers.length, 2);
  assert.equal(stroke(d, "stamp", [[110, 100]]), false, "selecting alone changes nothing");
  assert.equal(d.selected, 0);
  assert.equal(d.canUndo(), true); // (the two placements)
  const steps = d._undo.length;
  assert.equal(stroke(d, "stamp", [[110, 100], [130, 120]]), true);
  assert.deepEqual([d.stickers[0].x, d.stickers[0].y], [120, 120]); // grabbed 10 right of the centre, so the centre is 10 left
  assert.deepEqual([d.stickers[1].x, d.stickers[1].y], [200, 100]);
  assert.equal(d._undo.length, steps + 1, "a whole drag is one step");
  d.undo();
  assert.deepEqual([d.stickers[0].x, d.stickers[0].y], [100, 100]);
});

test("the topmost sticker is the one picked, and empty label places a new one", () => {
  const d = withStickers();
  d.stickerName = "full";
  stroke(d, "stamp", [[100, 100]]);
  stroke(d, "stamp", [[110, 100]]); // inside the first one: selects it, places nothing
  assert.equal(d.stickers.length, 1);
  stroke(d, "stamp", [[300, 150]]);
  assert.equal(d.stickers.length, 2);
  assert.equal(d.selected, 1, "the new one is selected");
  assert.equal(d.hit(300, 150), 1);
  assert.equal(d.hit(5, 5), -1);
});

test("resizing keeps the centre, clamps to the limits, and a slider drag is one undo step", () => {
  const d = withStickers({ scaleLimits: [1, 9] });
  d.stickerName = "full";
  stroke(d, "stamp", [[100, 100]]);
  const steps = d._undo.length;
  for (const scale of [3, 4, 5, 6]) assert.equal(d.resizeSelected(scale), true);
  assert.equal(d.resizeSelected(6), false, "no change, no step");
  assert.equal(d.stickers[0].scale, 6);
  assert.deepEqual([d.stickers[0].x, d.stickers[0].y], [100, 100]);
  assert.equal(d._undo.length, steps + 1);
  d.resizeSelected(50);
  assert.equal(d.stickers[0].scale, 9);
  d.resizeSelected(-4);
  assert.equal(d.stickers[0].scale, 1);
  d.undo();
  assert.equal(d.stickers[0].scale, 2, "back to the size it was placed at");
});

test("arrow-key nudges stay on the label and coalesce; delete removes the selected sticker and can be undone", () => {
  const d = withStickers();
  d.stickerName = "three";
  stroke(d, "stamp", [[0, 0]]);
  assert.equal(d.nudgeSelected(-1, -1), false, "already in the corner");
  for (let i = 0; i < 5; i++) d.nudgeSelected(1, 2);
  assert.deepEqual([d.stickers[0].x, d.stickers[0].y], [5, 10]);
  d.undo();
  assert.deepEqual([d.stickers[0].x, d.stickers[0].y], [0, 0], "five nudges were one step");
  d.redo();
  assert.equal(d.deleteSelected(), true);
  assert.equal(d.stickers.length, 0);
  assert.equal(d.selected, -1);
  assert.equal(d.deleteSelected(), false);
  d.undo();
  assert.equal(d.stickers.length, 1);
});

test("other tools deselect, ink and stickers undo together, and clear removes both", () => {
  const d = withStickers();
  d.stickerName = "three";
  stroke(d, "stamp", [[100, 100]]);
  d.brush = 1;
  stroke(d, "pen", [[10, 10]]);
  assert.equal(d.selected, -1);
  assert.equal(count(d), 1);
  assert.equal(d.isEmpty(), false);
  d.undo(); // the dot
  assert.equal(count(d), 0);
  assert.equal(d.stickers.length, 1);
  d.undo(); // the sticker
  assert.equal(d.isEmpty(), true);
  d.redo();
  d.redo();
  assert.equal(d.clear(), true);
  assert.equal(d.isEmpty(), true);
  d.undo();
  assert.equal(count(d), 1);
  assert.equal(d.stickers.length, 1);
});

test("the stamp ghost shows where a click would place one, half transparent, and not over a placed sticker", () => {
  const d = withStickers();
  d.stickerName = "full";
  d.stickerScale = 1;
  d.tool = "stamp";
  d.move(50, 50);
  assert.equal(alpha(rgbaOf(d), 50, 50), 128);
  assert.equal(count(d), 0, "a ghost is not ink");
  stroke(d, "stamp", [[200, 100]]);
  d.move(200, 100);
  d.up(200, 100);
  const rgba = rgbaOf(d);
  assert.equal(alpha(rgba, 200, 100), 255, "a placed sticker is solid");
  d.move(205, 100); // over the placed one: a click would grab it, so no ghost
  assert.equal(alpha(rgbaOf(d), 190, 100), 255);
  d.move(100, 20);
  assert.equal(alpha(rgbaOf(d), 100, 20), 128);
});

test("the selected sticker gets a dotted frame; the bucket treats stickers as walls", () => {
  const d = withStickers();
  d.stickerName = "full";
  d.stickerScale = 2;
  stroke(d, "stamp", [[100, 100]]);
  const rgba = rgbaOf(d);
  assert.equal(alpha(rgba, 100 - 24 - 2, 100 - 24 - 2), 255, "a frame dot just outside the corner");
  d.deselect();
  d.tool = "fill";
  d.down(100, 100); // on the sticker itself
  assert.equal(count(d), 0);
  d.down(10, 10); // on the open label: fills everything but the sticker
  assert.equal(at(d, 10, 10), 1);
  assert.equal(at(d, 100, 100), 0);
});

test("a stored sticker list is cleaned: unknown names dropped, scales clamped, no more than the limit", () => {
  const d = withStickers({ maxStickers: 2 });
  d.setStickers([{ name: "nope", x: 1, y: 1, scale: 1 }, { name: "full", x: 10.4, y: 20, scale: 99 }, { name: "three", x: 5, y: 5, scale: 0 }, { name: "three", x: 6, y: 6, scale: 2 }]);
  assert.deepEqual(d.stickers, [{ name: "full", x: 10, y: 20, scale: 9 }, { name: "three", x: 5, y: 5, scale: 1 }]);
  assert.equal(d.canUndo(), false);
  d.stickerName = "full";
  stroke(d, "stamp", [[300, 150]]);
  assert.equal(d.stickers.length, 2, "full: a click places nothing");
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
  const e = withStickers();
  e.stickerScale = 9;
  stroke(e, "stamp", [[0, 0], [W - 1, H - 1]]);
  rgbaOf(e);
  assert.equal(e.stickers.length, 1);
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
