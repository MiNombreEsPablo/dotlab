// The doodle tab: the tools, and a transparent layer laid over the preview to draw on, so you draw on the label itself.
// The drawing engine is doodle-raster.js; what the engine publishes (tools, inks, stickers, limits) comes from
// api.options(). The doodle is saved as the spec's `doodle` text: a base64 PNG, white dots = ink (see doodle.py).
// Placed stickers are not ink: they are the spec's `stickers` text (JSON, see stickers.py), a second control of this widget
// (`makeStickers`) so they can be selected, moved, resized and removed after they are placed.
//   createDoodleWidget(options) -> { make(field, notify), makeStickers(field, notify), overlay, setActive(bool), setUnderlay(gray) }

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
    const v = mask[i] ? 255 : 0;
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
    for (let i = 0; i < mask.length; i++) mask[i] = data[i * 4] > 127 ? 1 : 0;
    return mask;
  } catch (_) {
    return null;
  }
}

export function createDoodleWidget(options) {
  const info = options.doodle;
  const { width, height } = info;
  const stickerNames = Object.keys(options.stickers);
  const designs = Object.fromEntries(stickerNames.map((name) => [name, options.stickers[name].rows]));
  const doodle = new Doodle({ width, height, inks: info.inks, undoLimit: info.undo_limit, designs, scaleLimits: info.sticker_scale.slice(0, 2), maxStickers: info.max_stickers });

  const overlay = el("canvas", { className: "overlay", width, height, hidden: true });
  overlay.setAttribute("aria-label", "Draw on the label");
  overlay.tabIndex = 0; // focusable: a click on it takes focus (see pointerdown), so sticker keys work
  const context = overlay.getContext("2d");
  const buffer = new Uint8ClampedArray(width * height * 4);
  let queued = false;
  let inkColor = [0, 0, 0]; // the looks that tint the preview tint the ink with it
  const redraw = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      context.putImageData(new ImageData(doodle.toRgba(buffer, inkColor), width, height), 0, 0);
    });
  };

  let control = null; // the control the form holds (the menus clear it)
  let notifyStickers = () => {};
  let sentStickers = ""; // the stickers text the form last heard of
  const stickersText = () => (doodle.stickers.length ? JSON.stringify(doodle.stickers.map((s) => [s.name, s.x, s.y, s.scale])) : "");
  const stickersFrom = (text) => {
    try {
      const list = JSON.parse(text || "[]");
      return Array.isArray(list) ? list.filter((e) => Array.isArray(e) && e.length === 4 && e.slice(1).every(Number.isFinite)).map(([name, x, y, scale]) => ({ name, x, y, scale })) : [];
    } catch (_) {
      return [];
    }
  };
  let encoded = ""; // the doodle as text, kept until the ink changes again
  let stale = false;
  let active = false;

  function make(field, notify) {
    const tool = el("select", { id: "doodle-tool" });
    tool.setAttribute("aria-label", "Tool");
    for (const [value, label] of info.tools) tool.append(new Option(label, value));
    const ink = el("select", { id: "doodle-ink" });
    ink.setAttribute("aria-label", "Pattern");
    for (const [value, label] of info.inks) ink.append(new Option(label, value));
    const [bLo, bHi, bStart] = info.brush;
    const brush = makeSlider({ label: "Brush size", minimum: bLo, maximum: bHi, step: 1, scale: "linear", neutral: 0, zero_label: "", suffix: " dots",
      tip: "Width in dots (the eraser is twice as wide, the spray can sprays wider)" }, bStart, () => { doodle.brush = brush.get(); });
    const [sLo, sHi, sStart] = info.sticker_scale;
    const size = makeSlider({ label: "Sticker size", minimum: sLo, maximum: sHi, step: 1, scale: "linear", neutral: 0, zero_label: "", suffix: "×" },
      sStart, () => { doodle.stickerScale = size.get(); if (doodle.resizeSelected(size.get())) changed(); else redraw(); });
    doodle.brush = bStart;
    doodle.stickerScale = sStart;

    const grid = el("div", { className: "sticker-groups" });
    const buttons = [];
    for (const group of options.sticker_groups) {
      const part = el("div", { className: "stickers", role: "group" });
      part.setAttribute("aria-label", group.label);
      grid.append(el("span", { className: "group-title" }, group.label), part);
      for (const name of group.stickers) addSticker(part, name);
    }
    function addSticker(part, name) {
      const { label, rows } = options.stickers[name];
      const icon = el("canvas", { width: rows.length, height: rows.length });
      const ctx = icon.getContext("2d");
      rows.forEach((row, y) => [...row].forEach((c, x) => { if (c === "1") ctx.fillRect(x, y, 1, 1); }));
      const button = el("button", { type: "button", className: "sticker", title: label }, icon);
      button.setAttribute("aria-label", label);
      button.setAttribute("aria-pressed", String(name === stickerNames[0]));
      button.addEventListener("click", () => {
        doodle.stickerName = name;
        for (const b of buttons) b.setAttribute("aria-pressed", String(b === button));
        redraw();
      });
      buttons.push(button);
      part.append(button);
    }

    const snapBox = el("input", { type: "checkbox", id: "doodle-snap" });
    snapBox.setAttribute("aria-label", "Snap to grid");
    const snap = el("div", { className: "field toggles bare" }, el("div", { className: "checks" },
      el("label", { className: "check", title: "Graph paper: strokes, shapes and stickers land on the dots where the faint crosses are" }, snapBox, "Snap to grid")));
    const undo = el("button", { type: "button", className: "gel" }, "Undo");
    const redo = el("button", { type: "button", className: "gel" }, "Redo");
    const clear = el("button", { type: "button", className: "gel" }, "Clear");
    const remove = el("button", { type: "button", className: "gel" }, "Delete sticker");
    const row = (label, control, className = "") => el("div", { className: `field ${className}` }, el("span", { className: "row-title" }, label), control);
    const rows = {
      ink: row("Pattern", ink),
      brush: row("Brush", brush.root),
      sticker: row("Sticker", grid, "wide"),
      size: row("Size", size.root),
      remove: el("div", { className: "reset-row buttons" }, remove),
      hint: el("p", { className: "needs-hint doodle-hint" }, "Click the label to place a sticker. Click a placed one to select it: drag to move, the size slider resizes it, arrow keys nudge it, Delete removes it."),
    };
    const root = el("div", { className: "doodle-tools" },
      row("Tool", tool), rows.ink, rows.brush, rows.sticker, rows.size, rows.remove, rows.hint, snap,
      el("div", { className: "reset-row buttons" }, undo, redo, clear),
      el("p", { className: "needs-hint doodle-hint" }, "Scribble right on the label! Hold Shift for straight lines, squares and circles."));

    function syncTool() {
      doodle.tool = tool.value;
      if (tool.value !== "stamp") doodle.deselect();
      rows.ink.hidden = !info.uses_ink.includes(tool.value);
      rows.brush.hidden = !info.uses_brush.includes(tool.value);
      rows.sticker.hidden = rows.size.hidden = rows.remove.hidden = rows.hint.hidden = tool.value !== "stamp";
      syncButtons();
      redraw();
    }
    function syncButtons() {
      undo.disabled = !doodle.canUndo();
      redo.disabled = !doodle.canRedo();
      clear.disabled = doodle.isEmpty();
      const selected = doodle.selectedSticker();
      remove.disabled = !selected;
      if (selected && size.get() !== selected.scale) { // the slider shows the selected sticker's size
        size.set(selected.scale);
        doodle.stickerScale = selected.scale;
      }
    }
    function changed() {
      stale = true;
      syncButtons();
      redraw();
      notify();
      if (stickersText() !== sentStickers) {
        sentStickers = stickersText();
        notifyStickers();
      }
    }
    tool.addEventListener("input", syncTool);
    ink.addEventListener("input", () => { doodle.ink = ink.value; });
    snapBox.addEventListener("input", () => { doodle.showGrid = snapBox.checked; redraw(); });
    undo.addEventListener("click", () => { if (doodle.undo()) changed(); });
    redo.addEventListener("click", () => { if (doodle.redo()) changed(); });
    clear.addEventListener("click", () => { if (doodle.clear()) changed(); });
    remove.addEventListener("click", () => { if (doodle.deleteSelected()) changed(); });
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
      overlay.focus({ preventScroll: true }); // preventDefault stops the click moving focus: take it, so Delete and the arrows reach the sticker rather than a button or list left focused
      try { overlay.setPointerCapture(event.pointerId); } catch (_) { /* not an active pointer (a synthetic event): draw anyway */ }
      if (doodle.down(...at(event))) changed();
      else { syncButtons(); redraw(); } // (selecting a sticker changes nothing yet)
      if (doodle.tool === "spray") spray = setInterval(() => { if (doodle.sprayTick()) redraw(); }, info.spray_ms);
    });
    overlay.addEventListener("pointermove", (event) => {
      for (const e of (event.getCoalescedEvents && event.getCoalescedEvents().length ? event.getCoalescedEvents() : [event])) doodle.move(...at(e));
      overlay.style.cursor = doodle.tool === "stamp" && doodle.hit(...at(event)) >= 0 ? "move" : "";
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
      if (active && doodle.tool === "stamp" && doodle.selectedSticker() && !/^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(event.target.tagName) && !event.ctrlKey && !event.metaKey) {
        const step = event.shiftKey ? 10 : 1;
        const move = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[event.key];
        if (move || event.key === "Delete" || event.key === "Backspace") {
          event.preventDefault();
          if (move ? doodle.nudgeSelected(...move) : doodle.deleteSelected()) changed();
          return;
        }
      }
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

  function makeStickers(field, notify) { // the placed stickers, as the spec's `stickers` text; drawn by the doodle's own panel
    notifyStickers = notify;
    return {
      root: el("div", { hidden: true }),
      get: stickersText,
      set(text) {
        doodle.setStickers(stickersFrom(text));
        sentStickers = stickersText();
        redraw();
      },
      disable() {},
    };
  }

  return {
    make,
    makeStickers,
    current: () => control,
    overlay,
    setActive(on) { // only while the Doodle tab is open: elsewhere the engine draws the doodle into the preview itself
      active = on;
      overlay.hidden = !on;
      redraw();
    },
    setInk(rgb) {
      inkColor = rgb;
      redraw();
    },
    setUnderlay(gray) { // the label without its doodle: where its dark dots are, the paint bucket stops
      const dark = new Uint8Array(width * height);
      for (let i = 0; i < dark.length; i++) dark[i] = gray[i] < 128 ? 1 : 0;
      doodle.setUnderlay(dark);
    },
  };
}
