// The layers widget (the schema's "layers" field): the list of everything on the label (text, pictures, QR codes,
// stickers), one inspector for whichever is selected, and the selection box over the preview (drag to move, the corner
// handle resizes, arrows nudge, Delete removes). The Paper (background, border, bars) is the last entry of the list and is
// edited in the same inspector. The controls of each layer type come from api.options()["form"]["layer_fields"].
//   createLayersWidget(options, { image(field, notify) -> control, fonts(select) -> destroy, say(text, isError), paper() -> the label's
//   border, border_style and bars }) ->
//     { make(field, notify) -> control, overlay, setPaper(rows), setActive(on), usePicture(path, name, replace) -> bool,
//       syncPaper() (after the label was written), paperChanged() (the border or bars changed: layers that fill the old
//       usable area follow it) }
// The control's value is the label's `layers` text: JSON, bottom to top, only what differs from the defaults (see layers.py).

import { makeControl, valueOf, startValueOf, layoutFields } from "./form.js";
import { friendlyName } from "./image.js";

const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const PAPER = -2;
const NONE = -1;
const KINDS = { text: "Text", image: "Picture", qr: "QR code", sticker: "Sticker" };

// Does any visible layer say something? (as layers.has_content)
export function hasContent(text) {
  try {
    const list = JSON.parse(text || "[]");
    return Array.isArray(list) && list.some((l) => l && !l.hidden && ((l.text || "").trim() || (l.data || "").trim() || l.path || l.name));
  } catch (_) {
    return false;
  }
}

// The layers text without the pictures' paths (a path points into the engine's memory, which a reload empties), and
// whether there were any.
export function withoutPictures(text) {
  try {
    const list = JSON.parse(text || "[]");
    let had = false;
    for (const l of list) if (l && l.path) { had = true; l.path = ""; }
    return { text: had ? JSON.stringify(list) : text, had };
  } catch (_) {
    return { text, had: false };
  }
}

export function createLayersWidget(options, hooks) {
  const { types, max, min_box: minBox, defaults } = options.layers;
  const { width: W, sticker_height: SH, margin: MARGIN } = options.geometry;
  const layerFields = options.form.layer_fields;
  const stickerSide = (item) => (options.stickers[item.name] ? options.stickers[item.name].rows.length * item.scale : 24 * item.scale);
  const sizeOf = (item) => (item.t === "sticker" ? [stickerSide(item), stickerSide(item)] : [item.w, item.h]);

  let items = []; // bottom to top; each has every property of its type (defaults filled in)
  let selected = NONE;
  let notifyForm = () => {};
  let paperRows = [];
  let active = false;
  let inspectorControls = null; // {group, controls, nodes}: what the inspector shows now

  const { bar_height: barHeight, border_insets: insets } = options.geometry;
  const area = () => { // what is left inside the hazard bars and the border (as render.py laid the old arrangement out)
    let paper = {};
    try { paper = hooks.paper(); } catch (_) { /* the form is still being built: the plain label */ }
    const top = paper.bars ? barHeight : 0;
    const bottom = paper.bars ? SH - barHeight : SH;
    const margin = paper.border ? Math.max(MARGIN, (insets[paper.border_style] ?? 0) + 4) : MARGIN;
    return { x: margin, y: top + margin, w: W - 2 * margin, h: bottom - top - 2 * margin };
  };
  let seenArea = null;

  const full = (raw) => {
    const type = types.includes(raw && raw.t) ? raw.t : "text";
    const item = { ...defaults[type], ...raw, t: type };
    if (type === "sticker") [item.w, item.h] = sizeOf(item);
    return item;
  };
  const toText = () => {
    if (!items.length) return "";
    return JSON.stringify(items.map((item) => {
      const base = defaults[item.t];
      const out = { t: item.t };
      for (const key of Object.keys(item)) {
        if (key !== "t" && (["x", "y", "w", "h"].includes(key) || item[key] !== base[key])) out[key] = item[key];
      }
      return out;
    }));
  };

  // --- the list ---------------------------------------------------------------------------------------------------------
  const addBar = el("div", { className: "layer-add" });
  const list = el("ol", { className: "layer-list" });
  const inspector = el("div", { className: "inspector" });
  const root = el("div", { className: "layers" }, addBar, list, inspector);

  const nameOf = (item) => {
    if (item.t === "text") return (item.text.trim().split("\n")[0] || "(empty text)").slice(0, 28);
    if (item.t === "image") return item.path ? friendlyName(item.path) : "(no picture yet)";
    if (item.t === "qr") return item.data.trim().slice(0, 28) || "(empty QR code)";
    return (options.stickers[item.name] && options.stickers[item.name].label) || "Sticker";
  };

  function renderList() {
    list.replaceChildren();
    for (let i = items.length - 1; i >= 0; i--) list.append(row(i, items[i]));
    list.append(el("li", { className: "layer paper-entry" }, rowButton(PAPER, "Paper", "Background, border, bars")));
    for (const button of addButtons) button.disabled = items.length >= max;
  }
  function rowButton(index, title, subtitle) {
    const button = el("button", { type: "button", className: "layer-row" },
      el("span", { className: "layer-kind" }, title), el("span", { className: "layer-name" }, subtitle));
    button.setAttribute("aria-pressed", String(selected === index));
    button.addEventListener("click", () => select(index));
    return button;
  }
  function row(index, item) {
    const shown = el("input", { type: "checkbox", checked: !item.hidden, className: "layer-show" });
    shown.title = "Show or hide this layer";
    shown.setAttribute("aria-label", `Show ${KINDS[item.t]} layer`);
    shown.addEventListener("input", () => { // (the list is not rebuilt: that would take the keyboard focus away from this box)
      item.hidden = !shown.checked;
      emitLight();
    });
    return el("li", { className: "layer" }, shown, rowButton(index, KINDS[item.t], nameOf(item)));
  }

  function select(index) {
    selected = index;
    renderList();
    buildInspector();
    updateOverlay();
  }

  function add(type, over = {}) {
    if (items.length >= max) {
      hooks.say(`A label can have ${max} layers at most: delete one first.`, true);
      return false;
    }
    const room = area();
    let box = room;
    if (type === "text" && items.some((l) => l.t === "text")) box = { ...room, y: room.y + Math.round(room.h / 2), h: Math.round(room.h / 2) };
    if (type === "qr") box = { x: Math.round((W - 120) / 2), y: Math.round((SH - 120) / 2), w: 120, h: 120 };
    const item = full({ ...box, t: type, ...(type === "sticker" ? { name: "star", scale: 3 } : {}), ...over });
    if (type === "sticker") {
      item.x = Math.round((W - item.w) / 2);
      item.y = Math.round((SH - item.h) / 2);
    }
    items.push(item);
    selected = items.length - 1;
    notifyForm();
    select(selected);
    return true;
  }

  const addButtons = [];
  for (const type of types) {
    const button = el("button", { type: "button", className: "gel" }, `+ ${KINDS[type]}`);
    button.title = `Add a ${KINDS[type].toLowerCase()} layer`;
    button.addEventListener("click", () => add(type));
    addBar.append(button);
    addButtons.push(button);
  }

  function emit() { // the label changed: the form hears of it, the list and the selection box follow
    renderList();
    emitLight();
  }
  function emitLight() { // the same, when nothing the list shows has changed (a drag, a nudge, a show/hide)
    updateOverlay();
    notifyForm();
  }

  // --- the inspector ----------------------------------------------------------------------------------------------------
  let picker = null; // the sticker picker is built once (about 80 canvases) and reused by every sticker layer
  function stickerPicker(field, notify) {
    if (!picker) picker = buildStickerPicker();
    picker.notify = notify;
    return picker.control;
  }
  function buildStickerPicker() {
    const self = { notify: () => {}, control: null };
    let value = "";
    const buttons = new Map();
    const grid = el("div", { className: "sticker-groups" });
    const sections = new Map(); // name -> its <details>: the group holding the chosen sticker is the one that is open
    for (const group of options.sticker_groups) {
      const part = el("div", { className: "stickers", role: "group" });
      part.setAttribute("aria-label", group.label);
      const section = el("details", { className: "sticker-group" }, el("summary", {}, group.label), part);
      grid.append(section);
      for (const name of group.stickers) {
        sections.set(name, section);
        const { label, rows } = options.stickers[name];
        const icon = el("canvas", { width: rows.length, height: rows.length });
        const context = icon.getContext("2d");
        rows.forEach((line, y) => [...line].forEach((c, x) => { if (c === "1") context.fillRect(x, y, 1, 1); }));
        const button = el("button", { type: "button", className: "sticker", title: label }, icon);
        button.setAttribute("aria-label", label);
        button.addEventListener("click", () => {
          value = name;
          show();
          self.notify();
        });
        buttons.set(name, button);
        part.append(button);
      }
    }
    const show = () => buttons.forEach((b, name) => b.setAttribute("aria-pressed", String(name === value)));
    self.control = { root: grid, get: () => value, set: (v) => { value = v; show(); if (sections.has(v)) sections.get(v).open = true; }, disable() {} };
    return self;
  }

  let dropFonts = null; // takes the font picker's page-wide listener off before the inspector is rebuilt
  function buildInspector() {
    if (dropFonts) dropFonts();
    dropFonts = null;
    inspector.replaceChildren();
    inspectorControls = null;
    if (selected === PAPER) {
      inspector.append(el("h3", { className: "inspector-title" }, "Paper"),
        el("p", { className: "needs-hint" }, "The label itself: click the empty label to get here."), ...paperRows);
      return;
    }
    const item = items[selected];
    if (!item) {
      inspector.append(el("p", { className: "needs-hint" }, "Add a layer, or click one on the label."));
      return;
    }
    const mine = layerFields.filter((f) => f.tab === item.t);
    const box = layerFields.filter((f) => f.tab === "box" && (item.t !== "sticker" || f.name === "x" || f.name === "y"));
    const group = [...mine, ...box];
    const controls = new Map();
    const widgets = { image: hooks.image, sticker: stickerPicker };
    for (const field of group) {
      controls.set(field.name, makeControl(field, startValueOf(field, item), edited, widgets));
      if (field.kind === "image" || field.kind === "sticker") controls.get(field.name).set(item[field.name]); // (widgets start empty)
    }
    const { rows, nodes } = layoutFields(group, controls);
    inspectorControls = { group, controls, nodes };

    const footer = el("div", { className: "reset-row buttons" });
    const tool = (text, title, run, disabled = false) => {
      const button = el("button", { type: "button", className: "gel", title, disabled }, text);
      button.addEventListener("click", run);
      footer.append(button);
    };
    tool("Forward", "Move this layer above the next one", () => moveLayer(1), selected === items.length - 1);
    tool("Back", "Move this layer below the previous one", () => moveLayer(-1), selected === 0);
    tool("Duplicate", "Copy this layer", duplicate, items.length >= max);
    tool("Delete", "Remove this layer", remove);
    inspector.append(el("h3", { className: "inspector-title" }, KINDS[item.t]), ...rows, footer);
    refreshRules();
    const font = controls.get("font");
    if (font && font.input) dropFonts = hooks.fonts(font.input) || null;
  }

  function refreshRules() { // show_when / enable_when, as form.js does for the label's own fields
    if (!inspectorControls) return;
    const { group, controls, nodes } = inspectorControls;
    for (const f of group) {
      if (f.show_when.length) nodes.get(f.name).hidden = !f.show_when[1].includes(controls.get(f.show_when[0]).get());
      if (f.enable_when.length) controls.get(f.name).disable(!f.enable_when[1].includes(controls.get(f.enable_when[0]).get()));
    }
  }

  function edited() { // a control of the inspector changed: read them back into the layer
    const item = items[selected];
    if (!item || !inspectorControls) return;
    const { group, controls } = inspectorControls;
    const gated = new Set(group.map((f) => f.gate).filter(Boolean));
    for (const f of group) {
      if (!gated.has(f.name)) Object.assign(item, valueOf(f, controls.get(f.name), controls, item));
    }
    if (item.t === "sticker") [item.w, item.h] = sizeOf(item);
    refreshRules();
    emit();
  }
  function syncBox() { // the box was moved or resized on the label: the number boxes follow
    if (!inspectorControls) return;
    const item = items[selected];
    for (const [name, control] of inspectorControls.controls) {
      if (["x", "y", "w", "h", "scale"].includes(name)) control.set(item[name]);
    }
  }

  function moveLayer(by) {
    const to = selected + by;
    if (to < 0 || to >= items.length) return;
    [items[selected], items[to]] = [items[to], items[selected]];
    selected = to;
    notifyForm();
    select(selected);
  }
  function duplicate() {
    if (items.length >= max) return;
    const copy = { ...items[selected], x: items[selected].x + 8, y: items[selected].y + 8 };
    items.splice(selected + 1, 0, copy);
    notifyForm();
    select(selected + 1);
  }
  function remove() {
    if (!items[selected]) return;
    items.splice(selected, 1);
    selected = items.length ? Math.min(selected, items.length - 1) : NONE;
    notifyForm();
    select(selected);
  }

  // --- the selection box over the preview --------------------------------------------------------------------------------
  const frame = el("div", { className: "sel-box", hidden: true });
  const handle = el("div", { className: "sel-handle", title: "Drag to resize (Shift keeps the shape)" });
  frame.append(handle);
  const overlay = el("div", { className: "layers-overlay", tabIndex: 0, hidden: true }, frame);
  overlay.setAttribute("aria-label", "Layers on the label: click one to select it, drag to move, arrow keys nudge, Delete removes");

  function updateOverlay() {
    const item = items[selected];
    frame.hidden = !item;
    if (!item) return;
    const [w, h] = sizeOf(item);
    frame.style.left = `${(item.x / W) * 100}%`;
    frame.style.top = `${(item.y / SH) * 100}%`;
    frame.style.width = `${(w / W) * 100}%`;
    frame.style.height = `${(h / SH) * 100}%`;
  }

  const at = (event) => {
    const box = overlay.getBoundingClientRect();
    return [((event.clientX - box.left) / box.width) * W, ((event.clientY - box.top) / box.height) * SH];
  };
  function pick(x, y) { // the smallest visible layer under the point (a text box can cover the whole label); on a tie the top one
    let best = -1;
    let bestArea = Infinity;
    items.forEach((item, i) => {
      const [w, h] = sizeOf(item);
      if (item.hidden || x < item.x || y < item.y || x >= item.x + w || y >= item.y + h) return;
      if (w * h <= bestArea) [best, bestArea] = [i, w * h];
    });
    return best;
  }

  let drag = null;
  overlay.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    overlay.focus({ preventScroll: true });
    try { overlay.setPointerCapture(event.pointerId); } catch (_) { /* a synthetic event */ }
    const [x, y] = at(event);
    if (event.target === handle && items[selected]) {
      drag = { mode: "resize", x, y, item: items[selected], start: { ...items[selected] } };
      return;
    }
    const hit = pick(x, y);
    if (hit !== selected) select(hit >= 0 ? hit : PAPER);
    if (hit >= 0) drag = { mode: "move", x, y, item: items[hit], start: { ...items[hit] } };
  });
  overlay.addEventListener("pointermove", (event) => {
    if (!drag) {
      overlay.style.cursor = pick(...at(event)) >= 0 ? "move" : "";
      return;
    }
    const [x, y] = at(event);
    const [dx, dy] = [Math.round(x - drag.x), Math.round(y - drag.y)];
    const { item, start } = drag;
    if (drag.mode === "move") {
      item.x = start.x + dx;
      item.y = start.y + dy;
    } else if (item.t === "sticker") {
      const side = stickerSide(start) + Math.max(dx, dy);
      item.scale = clamp(Math.round(side / (stickerSide(start) / start.scale)), 1, options.layers.max_scale);
      [item.w, item.h] = sizeOf(item);
    } else {
      item.w = clamp(start.w + dx, minBox, W);
      item.h = event.shiftKey ? clamp(Math.round((item.w * start.h) / start.w), minBox, SH) : clamp(start.h + dy, minBox, SH);
    }
    syncBox();
    emitLight();
  });
  const release = () => { drag = null; };
  overlay.addEventListener("pointerup", release);
  overlay.addEventListener("pointercancel", release);
  overlay.addEventListener("keydown", (event) => {
    const item = items[selected];
    if (!item || event.ctrlKey || event.metaKey) return;
    const step = event.shiftKey ? 10 : 1;
    const move = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[event.key];
    if (move) {
      event.preventDefault();
      item.x += move[0];
      item.y += move[1];
      syncBox();
      emitLight();
    } else if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      remove();
    }
  });

  // --- what the form sees ------------------------------------------------------------------------------------------------
  function make(field, notify) {
    notifyForm = notify;
    const control = {
      root,
      get: toText,
      set(text) { // a stored label (a preset, a file, the last visit); "" is a new label, which starts with one empty text
        let raw = [];
        try { raw = JSON.parse(text || "[]"); } catch (_) { /* damaged: start again */ }
        items = (Array.isArray(raw) ? raw : []).filter((l) => l && typeof l === "object").slice(0, max).map(full);
        if (!items.length) items = [full({ t: "text", ...area() })];
        select(items.length - 1);
      },
      disable() {},
    };
    control.set(""); // a first visit starts with one empty text layer
    seenArea = area();
    return control;
  }

  return {
    make,
    overlay,
    setPaper(rows) { // the form's Paper controls, shown when the Paper entry is selected
      paperRows = rows;
      if (selected === PAPER) buildInspector();
    },
    setActive(on) { // the selection box is only there while the Layers tab is open
      active = on;
      overlay.hidden = !on;
    },
    isActive: () => active,
    syncPaper() { seenArea = area(); },
    paperChanged() { // the frame changed: a text or picture layer that filled the old usable area fills the new one
      const before = seenArea || area();
      seenArea = area();
      let changed = false;
      for (const item of items) {
        if ((item.t === "text" || item.t === "image") && item.x === before.x && item.y === before.y && item.w === before.w && item.h === before.h) {
          Object.assign(item, seenArea);
          changed = true;
        }
      }
      if (changed) {
        syncBox();
        emitLight();
      }
    },
    // a picture the user chose, dropped or pasted: `replace` (from a picture control) sets the selected picture layer's
    // picture; otherwise it fills an empty selected picture layer, or becomes a new layer
    usePicture(path, name, replace) {
      const item = items[selected];
      if (item && item.t === "image" && (replace || !item.path)) {
        item.path = path;
        emit();
        buildInspector();
        return true;
      }
      return add("image", { path }); // (at the limit, add says so and this is false)
    },
    selectedImage: () => !!(items[selected] && items[selected].t === "image"),
  };
}
