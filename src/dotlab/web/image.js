// The picture chooser (the schema's "image" field): shows which picture is chosen and lets the user browse, paste or
// remove it. Turning a file into something the engine can use is the page's job: it passes `useFile(file)`.
//   createImageWidget(useFile, say) -> { make(field, notify) -> control, current() }

const ACCEPT = "image/png,image/jpeg,image/bmp,image/gif,image/webp,.png,.jpg,.jpeg,.bmp,.gif,.webp";

const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
};

// A stored picture's file name without the hash the engine puts in front of it ("e521…-holiday.jpg" -> "holiday.jpg").
export function friendlyName(path) {
  const name = path.split("/").pop().replace(/^([0-9a-f]{12,16}-)+/, "");
  return /^[0-9a-f]{16}\.\w+$/.test(name) || !name ? "Picture" : name;
}

export function createImageWidget(useFile, say) {
  let widget = null;

  function make(field, notify) {
    let path = "";
    const nameLabel = el("span", { className: "picture-name" }, "No picture");
    const picker = el("input", { type: "file", accept: ACCEPT, hidden: true });
    const browse = el("button", { type: "button", className: "gel", title: field.tip || "" }, "Browse…");
    const pasteButton = el("button", { type: "button", className: "gel", title: "Paste a picture from the clipboard (Ctrl+V)" }, "Paste");
    const clear = el("button", { type: "button", className: "gel clear", hidden: true }, "×");
    clear.setAttribute("aria-label", "Remove the picture");
    browse.setAttribute("aria-label", "Choose a picture");
    const root = el("div", { className: "picture" }, nameLabel, browse, pasteButton, clear, picker);

    function set(newPath, shownName) {
      path = newPath || "";
      nameLabel.textContent = path ? shownName || friendlyName(path) : "No picture";
      nameLabel.title = path ? nameLabel.textContent : "";
      clear.hidden = !path;
    }
    browse.addEventListener("click", () => picker.click());
    picker.addEventListener("change", () => {
      const [file] = picker.files;
      picker.value = ""; // choosing the same file again must still fire
      if (file) useFile(file);
    });
    async function pasteFromClipboard() { // the Paste button and Edit > Paste image
      try {
        for (const item of await navigator.clipboard.read()) {
          const type = item.types.find((t) => t.startsWith("image/"));
          if (type) return useFile(new File([await item.getType(type)], "pasted picture", { type }));
        }
        say("There is no picture on the clipboard.");
      } catch (_) {
        say("The browser didn't allow reading the clipboard: click on the page and press Ctrl+V instead.");
      }
    }
    pasteButton.addEventListener("click", pasteFromClipboard);
    clear.addEventListener("click", () => {
      set("");
      notify();
    });

    widget = { root, get: () => path, set, paste: pasteFromClipboard, disable: (off) => { browse.disabled = pasteButton.disabled = clear.disabled = off; } };
    return widget;
  }
  return { make, current: () => widget };
}
