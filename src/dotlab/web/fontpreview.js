// The Font dropdown, drawn by us so every font's name shows in its own face.
//   previewFonts(select, options.fonts) -> destroy()   (call it before the select is thrown away: it takes the page-wide
//   listener and the observer off again; the font faces are declared once for the page, whoever asks first)
// Browsers draw a <select>'s list themselves and many ignore per-option fonts (Firefox on Linux, macOS, iOS), so the real
// <select> stays in the page, hidden, as the one source of truth (its value, its "input" event, form.js's get/set), and a
// button + list stand in front of it. The faces are declared and fetched only when the pointer or focus first reaches the
// button: the Japanese ones are 2-3 MB each, and a visitor who never opens the list shouldn't pay for them.

let declaredFaces = false; // the @font-face rules go into the page once, however many pickers are built

export function previewFonts(select, fonts) {
  const name = (family) => `Dotlab preview ${family}`;
  const css = (family) => `"${name(family)}", sans-serif`;
  const known = new Set(fonts.map((f) => f.family));
  const face = (value) => (known.has(value) ? { fontFamily: css(value) } : {});

  const button = document.createElement("button");
  button.type = "button";
  button.className = "pick";
  button.setAttribute("aria-haspopup", "listbox");
  button.setAttribute("aria-expanded", "false");
  const list = document.createElement("ul");
  list.className = "pick-list";
  list.setAttribute("role", "listbox");
  list.tabIndex = -1;
  list.hidden = true;
  const wrap = document.createElement("div");
  wrap.className = "pick-wrap";
  wrap.append(button, list);
  select.after(wrap);
  select.hidden = true;
  if (select.title) button.title = select.title;

  const items = []; // the list's <li role=option>, in order
  for (const child of select.children) {
    const group = child.tagName === "OPTGROUP" ? child : null;
    if (group) {
      const heading = document.createElement("li");
      heading.className = "pick-heading";
      heading.setAttribute("role", "presentation");
      heading.textContent = group.label;
      list.append(heading);
    }
    for (const option of group ? group.children : [child]) {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.dataset.value = option.value;
      li.textContent = option.textContent;
      Object.assign(li.style, face(option.value));
      list.append(li);
      items.push(li);
    }
  }

  let current = -1; // the highlighted item while the list is open
  const label = () => {
    const chosen = items.find((li) => li.dataset.value === select.value);
    button.textContent = chosen ? chosen.textContent : select.value;
    Object.assign(button.style, { fontFamily: "" }, face(select.value));
    for (const li of items) li.setAttribute("aria-selected", String(li === chosen));
  };
  // form.js sets `select.value` straight from code, with no event: follow it.
  const native = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value");
  Object.defineProperty(select, "value", {
    get() { return native.get.call(this); },
    set(v) { native.set.call(this, v); label(); },
  });
  const sync = () => {
    button.disabled = select.disabled;
  };
  label();

  const highlight = (index) => {
    if (items[current]) items[current].classList.remove("active");
    current = Math.max(0, Math.min(items.length - 1, index));
    items[current].classList.add("active");
    items[current].scrollIntoView({ block: "nearest" });
  };
  const isOpen = () => !list.hidden;
  const open = () => {
    if (isOpen() || button.disabled) return;
    list.hidden = false;
    button.setAttribute("aria-expanded", "true");
    highlight(Math.max(0, items.findIndex((li) => li.dataset.value === select.value)));
    items[current].scrollIntoView({ block: "center" });
  };
  const close = (refocus) => {
    if (!isOpen()) return;
    list.hidden = true;
    button.setAttribute("aria-expanded", "false");
    if (refocus) button.focus();
  };
  const choose = (li) => {
    close(true);
    if (li.dataset.value === select.value) return;
    select.value = li.dataset.value;
    select.dispatchEvent(new Event("input", { bubbles: true }));
    select.dispatchEvent(new Event("change", { bubbles: true }));
  };

  button.addEventListener("click", () => (isOpen() ? close(false) : open()));
  list.addEventListener("pointerdown", (event) => event.preventDefault()); // keep focus on the button
  list.addEventListener("click", (event) => {
    const li = event.target.closest("[role=option]");
    if (li) choose(li);
  });
  list.addEventListener("pointermove", (event) => {
    const li = event.target.closest("[role=option]");
    if (li && items[current] !== li) { items[current].classList.remove("active"); current = items.indexOf(li); li.classList.add("active"); }
  });
  button.addEventListener("keydown", (event) => {
    const key = event.key;
    if (!isOpen()) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(key)) { event.preventDefault(); open(); }
      return;
    }
    if (key === "ArrowDown") highlight(current + 1);
    else if (key === "ArrowUp") highlight(current - 1);
    else if (key === "Home") highlight(0);
    else if (key === "End") highlight(items.length - 1);
    else if (key === "Enter" || key === " ") choose(items[current]);
    else if (key === "Escape") close(true);
    else if (key === "Tab") close(false);
    else if (key.length === 1) { // type-ahead: the next name starting with that letter
      const at = items.findIndex((li, i) => i > current && li.textContent.toLowerCase().startsWith(key.toLowerCase()));
      const from = at >= 0 ? at : items.findIndex((li) => li.textContent.toLowerCase().startsWith(key.toLowerCase()));
      if (from >= 0) highlight(from);
      return;
    } else return;
    event.preventDefault();
  });
  button.addEventListener("blur", () => close(false));
  const outside = new AbortController();
  addEventListener("pointerdown", (event) => { if (!wrap.contains(event.target)) close(false); }, { signal: outside.signal });

  const declare = () => {
    if (declaredFaces) return;
    declaredFaces = true;
    const style = document.createElement("style");
    style.textContent = fonts.map((f) => {
      const file = f.files.regular || Object.values(f.files)[0];
      return `@font-face { font-family: "${name(f.family)}"; src: url("fonts/${encodeURIComponent(file)}") format("truetype"); font-weight: 100 900; font-display: swap; }`;
    }).join("\n");
    document.head.append(style);
    for (const f of fonts) document.fonts.load(`16px ${css(f.family)}`, f.family).catch(() => {});
  };
  for (const type of ["pointerenter", "pointerdown", "focus", "keydown"]) button.addEventListener(type, declare, { once: true });

  // form.js disables controls through `select.disabled`: mirror it.
  const watcher = new MutationObserver(sync);
  watcher.observe(select, { attributes: true, attributeFilter: ["disabled"] });
  sync();
  return () => {
    outside.abort();
    watcher.disconnect();
  };
}
