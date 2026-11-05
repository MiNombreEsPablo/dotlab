// An accessible menu bar (the ARIA menubar pattern) and the keyboard shortcuts its items name.
//   const bar = createMenubar(nav, menus);   bar.close()
// menus: [{ label, items: [ item | "-" ] }], where an item is
//   { label, run(), shortcut?: "Ctrl+O", enabled?(): bool, checked?(): bool (a radio item), heading?: "text", display?: true }
// `display: true` shows the shortcut without handling it (the browser already does: Ctrl+V pastes).
// Keys: Left/Right between menus, Down/Up in a menu, Home/End, Enter/Space to choose, Escape to close.

const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

function parse(shortcut) { // "Ctrl+Shift+C" -> {key: "c", shift: true}
  const parts = shortcut.toLowerCase().split("+");
  return { key: parts[parts.length - 1], shift: parts.includes("shift") };
}

export function createMenubar(nav, menus) {
  nav.setAttribute("role", "menubar");
  const titles = [];
  const lists = [];
  const entries = []; // per menu: [{item, button}]
  let open = -1;

  const enabledButtons = (index) => entries[index].filter((e) => e.button && !e.button.disabled).map((e) => e.button);

  function refreshItems(index) {
    for (const { item, button } of entries[index]) {
      if (!button) continue;
      button.disabled = item.enabled ? !item.enabled() : false;
      if (item.checked) button.setAttribute("aria-checked", String(!!item.checked()));
    }
  }
  function close(returnFocus = false) {
    if (open < 0) return;
    lists[open].hidden = true;
    titles[open].setAttribute("aria-expanded", "false");
    if (returnFocus) titles[open].focus();
    open = -1;
  }
  function show(index, focusFirst) {
    if (open === index) return;
    close();
    refreshItems(index);
    lists[index].hidden = false;
    titles[index].setAttribute("aria-expanded", "true");
    open = index;
    if (focusFirst) (enabledButtons(index)[0] || titles[index]).focus();
  }
  const neighbour = (index, step) => (index + step + menus.length) % menus.length;

  menus.forEach((menu, index) => {
    const title = el("button", { type: "button", className: "menu-title", role: "menuitem" }, menu.label);
    title.setAttribute("aria-haspopup", "menu");
    title.setAttribute("aria-expanded", "false");
    title.tabIndex = index === 0 ? 0 : -1;
    const list = el("ul", { className: "menu-list", role: "menu", hidden: true });
    list.setAttribute("aria-label", menu.label);
    const rows = [];
    for (const item of menu.items) {
      if (item === "-") {
        list.append(el("li", { role: "separator", className: "menu-separator" }));
        rows.push({ item });
      } else if (item.heading) {
        list.append(el("li", { role: "presentation", className: "menu-heading" }, item.heading));
        rows.push({ item });
      } else {
        const radio = !!item.checked;
        const button = el("button", { type: "button", className: "menu-item", role: radio ? "menuitemradio" : "menuitem" },
          el("span", { className: "menu-label" }, item.label), el("span", { className: "menu-shortcut" }, item.shortcut || ""));
        button.tabIndex = -1;
        button.addEventListener("click", async () => {
          close();
          nav.querySelectorAll(":focus").forEach((node) => node.blur());
          await item.run();
        });
        list.append(el("li", { role: "none" }, button));
        rows.push({ item, button });
      }
    }
    titles.push(title);
    lists.push(list);
    entries.push(rows);
    nav.append(el("div", { className: "menu" }, title, list));

    title.addEventListener("click", () => (open === index ? close() : show(index, false)));
    title.addEventListener("pointerenter", () => { if (open >= 0 && open !== index) show(index, false); });
    title.addEventListener("keydown", (event) => {
      const go = { ArrowRight: neighbour(index, 1), ArrowLeft: neighbour(index, -1), Home: 0, End: menus.length - 1 }[event.key];
      if (go !== undefined) {
        event.preventDefault();
        const was = open >= 0;
        close();
        titles.forEach((t, i) => { t.tabIndex = i === go ? 0 : -1; });
        titles[go].focus();
        if (was) show(go, false);
      } else if (["ArrowDown", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        show(index, true);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        show(index, false);
        const all = enabledButtons(index);
        (all[all.length - 1] || title).focus();
      } else if (event.key === "Escape") close();
    });
    list.addEventListener("keydown", (event) => {
      const all = enabledButtons(index);
      const at = all.indexOf(document.activeElement);
      const step = { ArrowDown: 1, ArrowUp: -1 }[event.key];
      if (step) {
        event.preventDefault();
        all[(at + step + all.length) % all.length].focus();
      } else if (event.key === "Home" || event.key === "End") {
        event.preventDefault();
        all[event.key === "Home" ? 0 : all.length - 1].focus();
      } else if (event.key === "Escape") {
        event.preventDefault();
        close(true);
      } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        const go = neighbour(index, event.key === "ArrowRight" ? 1 : -1);
        titles.forEach((t, i) => { t.tabIndex = i === go ? 0 : -1; });
        show(go, true);
      } else if (event.key === "Tab") close();
    });
  });

  addEventListener("pointerdown", (event) => { if (open >= 0 && !nav.contains(event.target)) close(); });
  addEventListener("blur", () => close());

  // the shortcuts the items name (the ones the browser or the page already handles are only displayed)
  addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.altKey || !(event.ctrlKey || event.metaKey)) return;
    const key = event.key.toLowerCase();
    for (const menu of menus) {
      for (const item of menu.items) {
        if (item === "-" || !item.shortcut || item.display) continue;
        const want = parse(item.shortcut);
        if (want.key === key && want.shift === event.shiftKey) {
          event.preventDefault();
          if (!item.enabled || item.enabled()) item.run();
          return;
        }
      }
    }
  });

  return { close };
}
