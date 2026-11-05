// Builds the label's controls from the description in api.options()["form"], so a choice added in Python shows up here
// without touching this file. The doodle and the printer are not described there; they have their own widgets, and
// the picture chooser is drawn by a widget the page passes in.
//   buildForm(schema, defaults, onChange, widgets) -> { tabs, output, read(), write(spec) }
// onChange(field) is called after the user changes a control; onTab(id) when a tab is opened (also for the first one).
// widgets.image / widgets.doodle(field, notify) -> a control (below), drawn by the page.
//
// Every control is { root: Element, get(), set(value), disable(bool) } with its value in the label's own units.

const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};
const decimals = (step) => (String(step).split(".")[1] || "").length;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// A slider and its number box. Log sliders spread a range like 0.3-3 evenly around `neutral` (two log scales meeting at
// the middle, as the Qt app does), so "no change" sits at the centre of the track like the zero of a symmetric slider.
export function makeSlider(field, startValue, notify) {
  const { minimum: min, maximum: max, step } = field;
  const places = decimals(step);
  const toInt = (v) => Math.round(v / step);
  const fromInt = (i) => Number((i * step).toFixed(places));
  const [lo, hi, mid] = [toInt(min), toInt(max), toInt(field.neutral)];
  const log = field.scale === "log";
  const STEPS = 1000;
  const half = STEPS / 2;
  const position = log
    ? (i) => (i <= mid ? Math.round((Math.log(Math.max(i, lo) / lo) / Math.log(mid / lo)) * half)
                       : half + Math.round((Math.log(i / mid) / Math.log(hi / mid)) * half))
    : (i) => i - lo;
  const fromPosition = log
    ? (p) => (p <= half ? Math.round(lo * Math.exp((p / half) * Math.log(mid / lo)))
                        : Math.round(mid * Math.exp(((p - half) / half) * Math.log(hi / mid))))
    : (p) => p + lo;

  const range = el("input", { type: "range", min: 0, max: log ? STEPS : hi - lo, step: 1 });
  const box = el("input", { type: "number", min, max, step, inputMode: log ? "decimal" : "numeric", className: "value" });
  if (field.zero_label) box.placeholder = field.zero_label;
  range.setAttribute("aria-label", field.label);
  box.setAttribute("aria-label", `${field.label} value`);
  if (field.tip) range.title = field.tip;
  let value = startValue;

  function show() {
    range.value = position(toInt(value));
    range.style.setProperty("--fill", `${(range.value / range.max) * 100}%`);
    box.value = field.zero_label && value === 0 ? "" : value.toFixed(places); // "1.0", as Qt shows it
  }
  function set(v) {
    value = clamp(fromInt(toInt(v)), min, max);
    show();
  }
  range.addEventListener("input", () => {
    value = clamp(fromInt(fromPosition(Number(range.value))), min, max);
    show();
    notify();
  });
  range.addEventListener("dblclick", () => {
    set(startValue);
    notify();
  });
  box.addEventListener("input", () => {
    const raw = box.value.trim();
    if (raw === "" && !field.zero_label) return;
    const n = raw === "" ? 0 : Number(raw);
    if (Number.isNaN(n)) return;
    value = clamp(fromInt(toInt(n)), min, max);
    range.value = position(toInt(value));
    range.style.setProperty("--fill", `${(range.value / range.max) * 100}%`);
    notify();
  });
  box.addEventListener("change", show); // tidy what was typed (clamped, rounded) once the box is left
  show();

  const root = el("div", { className: "slider" }, range, box, ...(field.suffix ? [el("span", { className: "suffix" }, field.suffix)] : []));
  return { root, get: () => value, set, disable: (off) => { range.disabled = box.disabled = off; } };
}

function makeControl(field, startValue, notify, widgets) {
  if (field.kind === "image") return widgets.image(field, notify);
  if (field.kind === "doodle") return widgets.doodle(field, notify);
  if (field.kind === "slider") return makeSlider(field, startValue, notify);
  const id = `f-${field.name}`;
  let input;
  switch (field.kind) {
    case "textarea": input = el("textarea", { id, rows: 3 }); break;
    case "text": input = el("input", { id, type: "text", autocomplete: "off" }); break;
    case "toggle": input = el("input", { id, type: "checkbox" }); break;
    case "number":
      input = el("input", { id, type: "number", min: field.minimum, max: field.maximum, step: 1, inputMode: "numeric" });
      if (field.zero_label) input.placeholder = field.zero_label;
      break;
    case "choice": {
      input = el("select", { id });
      if (field.none_label) input.append(new Option(field.none_label, ""));
      const groups = new Map();
      for (const [value, label, group] of field.choices) {
        if (!group) input.append(new Option(label, value));
        else {
          if (!groups.has(group)) groups.set(group, input.appendChild(el("optgroup", { label: group })));
          groups.get(group).append(new Option(label, value));
        }
      }
      break;
    }
    default: throw new Error(`unknown field kind ${field.kind}`);
  }
  if (field.tip) input.title = field.tip;
  input.addEventListener("input", notify);

  const get = () => {
    if (field.kind === "toggle") return input.checked;
    if (field.kind === "number") {
      const raw = input.value.trim();
      if (raw === "") return field.zero_label ? 0 : startValue;
      const n = Math.round(Number(raw));
      return Number.isNaN(n) ? startValue : clamp(n, field.minimum, field.maximum);
    }
    return input.value;
  };
  const set = (v) => {
    if (field.kind === "toggle") input.checked = !!v;
    else if (field.kind === "number") input.value = field.zero_label && v === 0 ? "" : v;
    else input.value = v;
  };
  set(startValue);
  let root = input;
  if (field.kind === "number" && field.suffix) root = el("span", { className: "suffixed" }, input, el("span", { className: "suffix" }, field.suffix));
  return { root, get, set, disable: (off) => { input.disabled = off; }, input };
}

// What a choice or a toggle contributes to the label: a "None" item turns a bool off; a gate sends a slider instead.
function valueOf(field, control, controls, defaults) {
  const v = control.get();
  if (field.kind === "choice" && field.toggle) return v === "" ? { [field.toggle]: false } : { [field.toggle]: true, [field.name]: v };
  if (field.kind === "choice" && field.gate) {
    return v === field.gate ? { [field.name]: "floyd", [field.gate]: controls.get(field.gate).get() } : { [field.name]: v, [field.gate]: null };
  }
  return { [field.name]: v };
}

function startValueOf(field, defaults) {
  if (field.kind === "choice" && field.toggle) return defaults[field.toggle] ? defaults[field.name] : "";
  if (field.kind === "choice" && field.gate) return defaults[field.gate] != null ? field.gate : defaults[field.name];
  if (field.kind === "slider") return defaults[field.name] ?? field.default;
  return defaults[field.name];
}

// Rows: consecutive fields with the same row title share one line under it.
function layoutFields(fields, controls) {
  const nodes = new Map(); // field name -> the row element it is in
  const rows = [];
  for (let i = 0; i < fields.length; i++) {
    const group = [fields[i]];
    while (fields[i].row && fields[i + 1] && fields[i + 1].row === fields[i].row) group.push(fields[++i]);
    const first = group[0];
    const allToggles = group.every((f) => f.kind === "toggle");
    let row;
    if (first.kind === "doodle") {
      row = controls.get(first.name).root; // the doodle's own panel, with its own rows
    } else if (allToggles) {
      const checks = group.map((f) => el("label", { className: "check" }, controls.get(f.name).root, f.label));
      row = el("div", { className: first.row ? "field toggles" : "field toggles bare" },
        ...(first.row ? [el("span", { className: "row-title" }, first.row)] : []),
        el("div", { className: "checks" }, ...checks));
    } else if (group.length === 1) {
      const control = controls.get(first.name);
      const label = el("label", { htmlFor: `f-${first.name}` }, first.label);
      row = el("div", { className: first.kind === "image" ? "field wide" : "field" },
        ...(first.kind === "image" ? [el("span", { className: "row-title" }, first.label)] : [label]), control.root);
    } else {
      row = el("div", { className: "field" }, el("span", { className: "row-title" }, first.row),
        el("div", { className: "inline" }, ...group.map((f) => controls.get(f.name).root)));
    }
    for (const f of group) nodes.set(f.name, row);
    rows.push(row);
  }
  return { rows, nodes };
}

export function buildForm(schema, defaults, onChange, widgets = {}, onTab = () => {}) {
  const fields = schema.fields;
  const byName = new Map(fields.map((f) => [f.name, f]));
  const controls = new Map();
  const rowOf = new Map();
  const gated = new Set(fields.map((f) => f.gate).filter(Boolean)); // sliders that only a gate field sends

  function refreshState() {
    const label = read();
    for (const tab of schema.tabs) {
      const active = !tab.needs || !!label[tab.needs];
      panelOf.get(tab.id).classList.toggle("dimmed", !active);
      hintOf.get(tab.id).hidden = active;
      for (const f of fields.filter((x) => x.tab === tab.id)) {
        const [watched, values] = f.enable_when.length ? f.enable_when : [null, []];
        const enabled = active && (!watched || values.includes(controls.get(watched).get()));
        controls.get(f.name).disable(!enabled);
        if (f.show_when.length) rowOf.get(f.name).hidden = !f.show_when[1].includes(controls.get(f.show_when[0]).get());
      }
      resetOf.get(tab.id) && (resetOf.get(tab.id).disabled = !active);
    }
  }
  const notifier = (field) => () => {
    refreshState();
    onChange(field);
  };

  for (const field of fields) {
    controls.set(field.name, makeControl(field, startValueOf(field, defaults), notifier(field), widgets));
  }
  const panelOf = new Map();
  const hintOf = new Map();
  const resetOf = new Map();

  function read() {
    const label = {};
    for (const field of fields) {
      if (gated.has(field.name)) continue;
      Object.assign(label, valueOf(field, controls.get(field.name), controls, defaults));
    }
    return label;
  }
  function write(spec) {
    const full = { ...defaults, ...spec };
    for (const f of fields) controls.get(f.name).set(startValueOf(f, full));
    refreshState();
  }

  // tabs: the ARIA tab pattern, arrows move between them
  const tablist = el("div", { className: "tablist", role: "tablist" });
  const panels = [];
  const buttons = [];
  schema.tabs.forEach((tab, index) => {
    const button = el("button", { type: "button", role: "tab", id: `tab-${tab.id}`, className: "tab" }, tab.label);
    button.setAttribute("aria-controls", `panel-${tab.id}`);
    const { rows, nodes } = layoutFields(fields.filter((f) => f.tab === tab.id), controls);
    for (const [name, row] of nodes) rowOf.set(name, row);
    const hint = el("p", { className: "needs-hint", hidden: true }, tab.needs_hint || "");
    const extras = [];
    if (tab.reset.length) {
      const reset = el("button", { type: "button", className: "gel reset", title: "Put every setting on this tab back to its default" }, "Reset");
      reset.addEventListener("click", () => {
        for (const name of tab.reset) controls.get(name).set(startValueOf(byName.get(name), defaults));
        refreshState();
        onChange(byName.get(tab.reset[0]));
      });
      resetOf.set(tab.id, reset);
      extras.push(el("div", { className: "reset-row" }, reset));
    }
    const panel = el("div", { role: "tabpanel", id: `panel-${tab.id}`, className: "panel" }, hint, ...rows, ...extras);
    panel.setAttribute("aria-labelledby", button.id);
    panelOf.set(tab.id, panel);
    hintOf.set(tab.id, hint);
    buttons.push(button);
    panels.push(panel);
    tablist.append(button);
    button.addEventListener("click", () => select(index, false));
    button.addEventListener("keydown", (event) => {
      const last = buttons.length - 1;
      const to = { ArrowRight: index === last ? 0 : index + 1, ArrowLeft: index === 0 ? last : index - 1, Home: 0, End: last }[event.key];
      if (to !== undefined) {
        event.preventDefault();
        select(to, true);
      }
    });
  });
  function select(index, focus) {
    buttons.forEach((button, i) => {
      button.setAttribute("aria-selected", String(i === index));
      button.tabIndex = i === index ? 0 : -1;
      panels[i].hidden = i !== index;
    });
    if (focus) buttons[index].focus();
    onTab(schema.tabs[index].id);
  }
  select(0, false);

  const outputLayout = layoutFields(fields.filter((f) => f.tab === "output"), controls);
  const output = el("fieldset", { className: "output" }, el("legend", {}, "Output"), ...outputLayout.rows);
  refreshState();

  return { tabs: el("div", { className: "tabs" }, tablist, ...panels), output, read, write, refreshState };
}
