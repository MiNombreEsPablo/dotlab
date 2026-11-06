// The doodle tab: the tools, and a transparent layer laid over the preview to draw on, so you draw on the label itself.
// The drawing engine is doodle-raster.js; what the engine publishes (tools, inks, limits) comes from
// api.options(). The doodle is saved as the spec's `doodle` text: a base64 PNG: white dots = black ink, mid-grey = white ink (see doodle.py).
// (Stickers are layers now: see layers.js.)
//   createDoodleWidget(options) -> { make(field, notify), overlay, setActive(bool), setUnderlay(gray) }

import { Doodle } from "./doodle-raster.js";
import { makeSlider } from "./form.js";

const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
const PNG_PREFIX = "data:image/png;base64,";

function pngFromMask(mask, width, height) { // "" when nothing is drawn
  if (!mask.some((v) => v)) return "";
  const canvas = el("canvas", { width, height });
  const context = canvas.getContext("2d");
  const image = context.createImageData(width, height);
  for (let i = 0; i < mask.length; i++) {
    const v = mask[i] === 2 ? 128 : mask[i] ? 255 : 0;
    image.data[i * 4] = image.data[i * 4 + 1] = image.data[i * 4 + 2] = v;
    image.data[i * 4 + 3] = 255;
  }
  context.putImageData(image, 0, 0);
  return canvas.toDataURL("image/png").slice(PNG_PREFIX.length);
}

async function maskFromPng(base64, width, height) { // null for anything that isn't a doodle of this size
  if (!base64) return new Uint8Array(width * height);
  try {
    const image = new Image();
    image.src = PNG_PREFIX + base64;
    await image.decode();
    if (image.width !== width || image.height !== height) return null;
    const canvas = el("canvas", { width, height });
    const context = canvas.getContext("2d");
    context.drawImage(image, 0, 0);
    const data = context.getImageData(0, 0, width, height).data;
    const mask = new Uint8Array(width * height);
    for (let i = 0; i < mask.length; i++) mask[i] = data[i * 4] > 191 ? 1 : data[i * 4] > 63 ? 2 : 0;
    return mask;
  } catch (_) {
    return null;
  }
}

export function createDoodleWidget(options) {
  const info = options.doodle;
  const { width, height } = info;
  const doodle = new Doodle({ width, height, inks: info.inks, undoLimit: info.undo_limit });

  const overlay = el("canvas", { className: "overlay", width, height, hidden: true });
  overlay.setAttribute("aria-label", "Draw on the label");
  overlay.tabIndex = 0; // focusable: a click on it takes focus (see pointerdown), so the keyboard shortcuts work
  const context = overlay.getContext("2d");
  const buffer = new Uint8ClampedArray(width * height * 4);
  let queued = false;
  let inkColor = [0, 0, 0]; // the looks that tint the preview tint the ink with it
  let paperColor = [255, 255, 255]; // ... and the white ink with the paper
  const redraw = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      context.putImageData(new ImageData(doodle.toRgba(buffer, inkColor, paperColor), width, height), 0, 0);
    });
  };

  let control = null; // the control the form holds (the menus clear it)
  let encoded = ""; // the doodle as text, kept until the ink changes again
  let stale = false;
  let active = false;

  function make(field, notify) {
    const tool = el("select", { id: "doodle-tool" });
    tool.setAttribute("aria-label", "Tool");
    for (const [value, label] of info.tools) tool.append(new Option(label, value));
    const colour = el("select", { id: "doodle-colour" });
    colour.setAttribute("aria-label", "Ink");
    colour.append(new Option("Black", "1"), new Option("White (lightens a dark picture)", "2"));
    const ink = el("select", { id: "doodle-ink" });
    ink.setAttribute("aria-label", "Pattern");
    for (const [value, label] of info.inks) ink.append(new Option(label, value));
    const [bLo, bHi, bStart] = info.brush;
    const brush = makeSlider({ label: "Brush size", minimum: bLo, maximum: bHi, step: 1, scale: "linear", neutral: 0, zero_label: "", suffix: " dots",
      tip: "Width in dots (the eraser is twice as wide, the spray can sprays wider)" }, bStart, () => { doodle.brush = brush.get(); });
    doodle.brush = bStart;

    const snapBox = el("input", { type: "checkbox", id: "doodle-snap" });
    snapBox.setAttribute("aria-label", "Snap to grid");
    const snap = el("div", { className: "field toggles bare" }, el("div", { className: "checks" },
      el("label", { className: "check", title: "Graph paper: strokes and shapes land on the dots where the faint crosses are" }, snapBox, "Snap to grid")));
    const undo = el("button", { type: "button", className: "gel" }, "Undo");
    const redo = el("button", { type: "button", className: "gel" }, "Redo");
    const clear = el("button", { type: "button", className: "gel" }, "Clear");
    const row = (label, control, className = "") => el("div", { className: `field ${className}` }, el("span", { className: "row-title" }, label), control);
    const rows = {
      colour: row("Ink", colour),
      ink: row("Pattern", ink),
      brush: row("Brush", brush.root),
    };
    const root = el("div", { className: "doodle-tools" },
      row("Tool", tool), rows.colour, rows.ink, rows.brush, snap,
      el("div", { className: "reset-row buttons" }, undo, redo, clear),
      el("p", { className: "needs-hint doodle-hint" }, "Scribble right on the label! Hold Shift for straight lines, squares and circles."));

    function syncTool() {
      doodle.tool = tool.value;
      rows.colour.hidden = tool.value === "eraser";
      rows.ink.hidden = !info.uses_ink.includes(tool.value);
      rows.brush.hidden = !info.uses_brush.includes(tool.value);
      syncButtons();
      redraw();
    }
    function syncButtons() {
      undo.disabled = !doodle.canUndo();
      redo.disabled = !doodle.canRedo();
      clear.disabled = doodle.isEmpty();
    }
    function changed() {
      stale = true;
      syncButtons();
      redraw();
      notify();
    }
    tool.addEventListener("input", syncTool);
    ink.addEventListener("input", () => { doodle.ink = ink.value; });
    colour.addEventListener("input", () => { doodle.color = Number(colour.value); });
    snapBox.addEventListener("input", () => { doodle.showGrid = snapBox.checked; redraw(); });
    undo.addEventListener("click", () => { if (doodle.undo()) changed(); });
    redo.addEventListener("click", () => { if (doodle.redo()) changed(); });
    clear.addEventListener("click", () => { if (doodle.clear()) changed(); });
    syncTool();
    syncButtons();

    // --- pointer: mouse, pen and touch alike -------------------------------------------------------------------
    const at = (event) => {
      const box = overlay.getBoundingClientRect();
      const x = Math.min(width - 1, Math.max(0, Math.floor(((event.clientX - box.left) / box.width) * width)));
      const y = Math.min(height - 1, Math.max(0, Math.floor(((event.clientY - box.top) / box.height) * height)));
      doodle.constrain = event.shiftKey; // Shift is read with every position, so letting go mid-drag lets go of the constraint
      return doodle.showGrid ? doodle.snap(x, y) : [x, y];
    };
    let spray = null;
    const stopSpray = () => { clearInterval(spray); spray = null; };
    overlay.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      overlay.focus({ preventScroll: true }); // preventDefault stops the click moving focus: take it, so the shortcuts reach the canvas rather than a button left focused
      try { overlay.setPointerCapture(event.pointerId); } catch (_) { /* not an active pointer (a synthetic event): draw anyway */ }
      if (doodle.down(...at(event))) changed();
      else { syncButtons(); redraw(); }
      if (doodle.tool === "spray") spray = setInterval(() => { if (doodle.sprayTick()) redraw(); }, info.spray_ms);
    });
    overlay.addEventListener("pointermove", (event) => {
      for (const e of (event.getCoalescedEvents && event.getCoalescedEvents().length ? event.getCoalescedEvents() : [event])) doodle.move(...at(e));
      redraw();
    });
    const finish = (event) => {
      stopSpray();
      if (doodle.up(...at(event))) changed();
    };
    overlay.addEventListener("pointerup", (event) => { finish(event); syncButtons(); redraw(); });
    overlay.addEventListener("pointercancel", () => { stopSpray(); doodle.cancel(); changed(); });
    overlay.addEventListener("pointerleave", () => { doodle.leave(); redraw(); });
    addEventListener("keydown", (event) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName) && event.target.type !== "range";
      if (active && !typing && (event.ctrlKey || event.metaKey)) {
        const key = event.key.toLowerCase();
        if (key === "z" || key === "y") {
          event.preventDefault();
          if (key === "y" || event.shiftKey ? doodle.redo() : doodle.undo()) changed();
        }
      }
    });

    control = {
      root,
      get() {
        if (stale) { encoded = pngFromMask(doodle.pixels, width, height); stale = false; }
        return encoded;
      },
      set(text) { // a stored doodle (a preset, a file)
        // its text is the label's doodle from this moment (the engine draws it from the text: the very next render must
        // see it); decoding it into the canvas only matters for drawing on top of it, and can take a moment
        encoded = text;
        stale = false;
        maskFromPng(text, width, height).then((mask) => {
          if (encoded !== text) return; // something newer was set or drawn meanwhile
          doodle.setMask(mask || new Uint8Array(width * height));
          if (!mask) encoded = ""; // damaged: the engine would ignore it anyway
          syncButtons();
          redraw();
        });
      },
      disable() {},
      clear() { if (doodle.clear()) changed(); },
    };
    return control;
  }

  return {
    make,
    current: () => control,
    overlay,
    setActive(on) { // only while the Doodle tab is open: elsewhere the engine draws the doodle into the preview itself
      active = on;
      overlay.hidden = !on;
      redraw();
    },
    setInk(rgb, paper = [255, 255, 255]) {
      inkColor = rgb;
      paperColor = paper;
      redraw();
    },
    setUnderlay(gray) { // the label without its doodle: where its dark dots are, the paint bucket stops
      const dark = new Uint8Array(width * height);
      for (let i = 0; i < dark.length; i++) dark[i] = gray[i] < 128 ? 1 : 0;
      doodle.setUnderlay(dark);
    },
  };
}
