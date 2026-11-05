// The UI, written once. It only ever talks to three seams, whichever client it runs in:
//   engine:  options(), preview(spec) -> {pixels, hints}                 (engine/pyodide.js)
//   printer: modes, print(spec, {mode}) -> {problems, error}    (printer/index.js: ble.js or serial.js)
//   store:   get(key, fallback), set(key, value)                         (store/local.js)
//   files:   save(bytes, name, mime, kind), copyImage(png)              (files/browser.js)
//   presets: list(), get(name), save(name, label), delete(name)          (presets/local.js)
// The label's simple controls are built from the description the engine provides (form.js).

import { buildForm } from "./form.js";
import { createImageWidget } from "./image.js";
import { createDoodleWidget } from "./doodle.js";
import { createMenubar } from "./menus.js";
import { applyTheme, DEFAULT_THEME, previewColors, THEMES } from "./themes.js";

const $ = (id) => document.getElementById(id);
const status = (text, isError = false) => {
  $("status").textContent = text;
  $("status").classList.toggle("error", isError);
};

async function connectSeams() {
  const [engineModule, printerModule, storeModule, filesModule, presetsModule] = await Promise.all([
    import("./engine/pyodide.js"), import("./printer/index.js"), import("./store/local.js"), import("./files/browser.js"),
    import("./presets/local.js"),
  ]);
  const engine = engineModule.createEngine(new URL("./", location.href).href);
  await engine.init(status);
  return {
    engine, store: storeModule.createStore(), files: filesModule.createFiles(), presets: presetsModule.createPresets(engine),
    makePrinter: (options) => printerModule.createPrinter(engine, options),
  };
}

async function main() {
  status("Starting…");
  const { engine, store, files, presets, makePrinter } = await connectSeams();
  const options = await engine.options();
  const printer = makePrinter(options);
  const { width, sticker_height: stickerHeight } = options.geometry;

  const canvas = $("preview");
  canvas.width = width;
  canvas.height = stickerHeight; // the gap between stickers is never printed: the page captions it under the canvas
  const context = canvas.getContext("2d");

  // Render the newest request only: while one is running, later keystrokes just replace the waiting one.
  let rendering = false;
  let again = false;
  let last = null;
  async function refresh() {
    if (rendering) {
      again = true;
      return;
    }
    rendering = true;
    try {
      do {
        again = false;
        // while drawing, the engine renders the label without its doodle: the overlay shows the ink, and the bucket
        // needs the label alone to know where the text is
        const { pixels, hints } = await engine.preview(activeTab === "doodle" ? { ...spec(), doodle: "" } : spec());
        draw(pixels);
        if (activeTab === "doodle") doodle.setUnderlay(pixels);
        $("hint").textContent = hints.join(" ");
        $("hint").hidden = hints.length === 0;
      } while (again);
      if ($("status").classList.contains("error")) status("");
    } catch (e) {
      status(`Couldn't draw the label: ${e.message}`, true);
    } finally {
      rendering = false;
    }
  }

  // a picture the user chose, dropped or pasted: the engine takes it in and hands back the path the label uses
  async function useFile(file) {
    if (!file) return;
    status(`Reading ${file.name}…`);
    const started = performance.now();
    try {
      const path = await engine.addImage(new Uint8Array(await file.arrayBuffer()), file.name);
      picture.current().set(path, file.name);
      form.refreshState();
      status("");
      await refresh();
      const seconds = (performance.now() - started) / 1000;
      if (seconds > 1.5) status(`${file.name} (${(file.size / 1e6).toFixed(1)} MB) took ${seconds.toFixed(1)} s to load.`);
    } catch (e) {
      status(`Couldn't use that picture: ${e.message}`, true);
    }
  }
  const picture = createImageWidget(useFile, (text) => status(text, true));
  const doodle = createDoodleWidget(options);
  document.querySelector(".paper").append(doodle.overlay);
  let activeTab = "";
  const form = buildForm(options.form, options.defaults, (field) => {
    if (field.tab === "output") return; // copies and darkness don't change the picture
    if (field.name === "doodle" && activeTab === "doodle") return; // the overlay already shows what was drawn
    refresh();
  }, { image: picture.make, doodle: doodle.make }, (id) => {
    const wasDrawing = activeTab === "doodle";
    activeTab = id;
    doodle.setActive(id === "doodle");
    if (wasDrawing || id === "doodle") refresh(); // the doodle moves between the engine's picture and the overlay
  });

  const pictureIn = (transfer) => Array.from((transfer && transfer.files) || []).find((f) => f.type.startsWith("image/"));
  addEventListener("dragover", (event) => {
    if (Array.from(event.dataTransfer.items || []).some((i) => i.kind === "file")) {
      event.preventDefault();
      document.body.classList.add("dropping");
    }
  });
  addEventListener("dragleave", (event) => {
    if (!event.relatedTarget) document.body.classList.remove("dropping");
  });
  addEventListener("drop", (event) => {
    document.body.classList.remove("dropping");
    const file = pictureIn(event.dataTransfer);
    if (file) {
      event.preventDefault();
      openOrUse(file);
    }
  });
  addEventListener("paste", (event) => { // a picture on the clipboard wins even in a text box; text pastes as usual
    const file = pictureIn(event.clipboardData);
    if (file) {
      event.preventDefault();
      useFile(file);
    }
  });
  const spec = () => form.read();
  $("form").append(form.tabs);

  // the printer row belongs to the Output box but differs per client, so it isn't in the form description
  fill($("mode"), printer.modes);
  const saved = await store.get("printer", {});
  if (printer.modes.includes(saved.mode)) $("mode").value = saved.mode;
  $("printer-row").hidden = printer.modes.length < 2;
  $("mode").addEventListener("input", () => store.set("printer", { mode: $("mode").value }));
  form.output.append($("printer-row"));
  $("output").append(form.output);

  function draw(gray) {
    last = gray;
    const { ink, paper } = previewColors(); // black on white, or the tint of the chosen look
    const image = context.createImageData(width, stickerHeight);
    for (let i = 0; i < width * stickerHeight; i++) {
      image.data.set(gray[i] < 128 ? ink : paper, i * 4);
      image.data[i * 4 + 3] = 255;
    }
    context.putImageData(image, 0, 0);
  }

  // the look: remembered, applied at once; the preview and the doodle ink follow its tint
  const retint = () => {
    if (last) draw(last);
    doodle.setInk(previewColors().ink);
  };
  let currentTheme = applyTheme(await store.get("theme", DEFAULT_THEME));
  retint();
  function setTheme(key) {
    currentTheme = applyTheme(key);
    store.set("theme", currentTheme);
    retint();
  }

  const hasContent = (label) => options.content_fields.some((name) => String(label[name]).trim()); // as spec.has_content

  // saving and copying the label as an image: the engine renders the PNG, the files seam delivers it
  for (const [scale, name] of options.export.scales) $("export-size").append(new Option(name, scale));
  $("export-size").value = await store.get("exportScale", options.export.scales[0][0]);
  $("export-size").addEventListener("input", () => store.set("exportScale", Number($("export-size").value)));
  async function makeImage(doing) {
    const current = spec();
    if (!hasContent(current)) {
      status(`Nothing to ${doing}.`);
      return null;
    }
    return engine.exportPng(current, Number($("export-size").value));
  }
  async function saveImage() {
    try {
      const image = await makeImage("save");
      if (!image) return;
      const result = await files.save(image.data, image.name, "image/png", "PNG image");
      if (result.error) status(result.error, true);
      else if (!result.cancelled) status(`Saved ${result.saved}.`);
    } catch (e) {
      status(`Couldn't save the image: ${e.message}`, true);
    }
  }
  async function copyImage() {
    try {
      const image = await makeImage("copy");
      if (!image) return;
      await files.copyImage(image.data);
      status("Copied the label to the clipboard.");
    } catch (e) {
      status(`Couldn't copy the image: ${e.message}`, true);
    }
  }
  $("save-image").addEventListener("click", saveImage);
  $("copy-image").addEventListener("click", copyImage);

  // presets: named styles (the label without its picture); choosing one replaces the label, as in the Qt app
  const NO_PRESET = "— presets —";
  async function reloadPresets(select = "") {
    const names = await presets.list();
    $("preset").replaceChildren(new Option(NO_PRESET, ""), ...names.map((name) => new Option(name, name)));
    $("preset").value = names.includes(select) ? select : "";
    resetDelete();
  }
  let deleteTimer = null;
  function resetDelete() {
    clearTimeout(deleteTimer);
    $("preset-delete").textContent = "Delete";
    $("preset-delete").disabled = !$("preset").value;
  }
  function closeNameForm() {
    $("preset-name-form").hidden = true;
    $("preset-save").hidden = false;
  }
  try {
    await reloadPresets();
  } catch (_) {
    document.querySelector(".presets").hidden = true; // storage that can't even be read: no preset bar rather than a broken one
  }
  $("preset").addEventListener("input", async () => {
    resetDelete();
    const name = $("preset").value;
    if (!name) return;
    const loaded = await presets.get(name);
    if (!loaded) {
      status(`There is no preset called “${name}”.`, true);
      return reloadPresets();
    }
    form.write(loaded);
    status("");
    await refresh();
  });
  $("preset-save").addEventListener("click", () => {
    $("preset-save").hidden = true;
    $("preset-name-form").hidden = false;
    $("preset-name").value = $("preset").value;
    $("preset-name").focus();
    $("preset-name").select();
  });
  $("preset-cancel").addEventListener("click", closeNameForm);
  $("preset-name").addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeNameForm();
  });
  $("preset-name-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const saved = await presets.save($("preset-name").value, spec());
      closeNameForm();
      await reloadPresets(saved);
      status(`Saved preset “${saved}”.${spec().image_path ? " (A preset keeps the style, not the picture: Save label… keeps both.)" : ""}`);
    } catch (e) {
      status(`Couldn't save the preset: ${e.message}`, true);
    }
  });
  $("preset-delete").addEventListener("click", async () => {
    const name = $("preset").value;
    if (!name) return;
    if ($("preset-delete").textContent === "Delete") { // the first click asks; a second one soon after does it
      $("preset-delete").textContent = "Really delete?";
      deleteTimer = setTimeout(resetDelete, 4000);
      return;
    }
    try {
      await presets.delete(name);
      await reloadPresets();
      status(`Deleted preset “${name}”.`);
    } catch (e) {
      status(`Couldn't delete the preset: ${e.message}`, true);
    }
  });

  // the whole label design as a label file (a PNG with the design inside; the picture travels inside it), and back
  async function openLabelFile(file) {
    try {
      form.write(await engine.compositionLoads(new Uint8Array(await file.arrayBuffer())));
      status(`Opened ${file.name}.`);
      await refresh();
    } catch (e) {
      status(`Couldn't open ${file.name}: ${e.message}`, true);
    }
  }
  // a dropped PNG saved by Dotlab opens as the label it holds; any other picture becomes the label's picture
  async function openOrUse(file) {
    if (file.type === "image/png" || file.name.toLowerCase().endsWith(".png")) {
      try {
        const label = await engine.compositionLoads(new Uint8Array(await file.arrayBuffer()));
        form.write(label);
        status(`Opened ${file.name}.`);
        return refresh();
      } catch (_) { /* only a picture */ }
    }
    return useFile(file);
  }
  $("open-label").addEventListener("click", () => $("label-file").click());
  $("label-file").addEventListener("change", () => {
    const [file] = $("label-file").files;
    $("label-file").value = "";
    if (file) openLabelFile(file);
  });
  async function saveLabel() {
    try {
      const file = await engine.compositionDumps(spec());
      const result = await files.save(file.data, file.name, options.composition.mime, "Dotlab label (PNG)");
      if (result.error) status(result.error, true);
      else if (!result.cancelled) status(`Saved ${result.saved}.`);
    } catch (e) {
      status(`Couldn't save the label: ${e.message}`, true);
    }
  }
  $("save-label").addEventListener("click", saveLabel);

  async function print() {
    const current = spec();
    if (!hasContent(current)) return status("Nothing to print.");
    $("print").disabled = true;
    status("Printing…");
    const result = await printer.print(current, { mode: $("mode").value });
    $("print").disabled = false;
    if (result.error) status(result.error, true);
    else status(result.problems.length ? `Printer: ${result.problems.join(", ")}` : "Sent.");
  }
  $("print").addEventListener("click", print);
  $("print").disabled = false;

  // the menu bar: every item calls an action the buttons already use
  async function clearImage() {
    picture.current().set("");
    form.refreshState();
    await refresh();
  }
  function showAbout() {
    const app = options.app;
    $("about-title").textContent = `${app.name} ${app.version}`;
    $("about-details").textContent = `Includes ${app.fonts} bundled open-source font families (SIL Open Font License).`;
    $("about-repo").href = app.repo_url;
    $("about").showModal();
  }
  $("about-repo").addEventListener("click", (event) => {
    event.preventDefault();
    openLink(options.app.repo_url);
  });
  async function openLink(url) {
    try {
      await files.openLink(url);
    } catch (e) {
      status(`Couldn't open the page: ${e.message}`, true);
    }
  }
  createMenubar($("menubar"), [
    { label: "File", items: [
      { label: "Open label…", shortcut: "Ctrl+O", run: () => $("label-file").click() },
      { label: "Save label…", shortcut: "Ctrl+S", run: saveLabel },
      "-",
      { label: "Save image…", shortcut: "Ctrl+E", run: saveImage },  // (always on: with nothing to save, the action says so)
      { label: "Print", shortcut: "Ctrl+P", run: print, enabled: () => !$("print").disabled },
    ] },
    { label: "Edit", items: [
      { label: "Paste image", shortcut: "Ctrl+V", display: true, run: () => picture.current().paste() },
      { label: "Clear image", run: clearImage, enabled: () => !!spec().image_path },
      { label: "Clear doodle", run: () => doodle.current().clear(), enabled: () => !!spec().doodle },
      "-",
      { label: "Copy label as image", shortcut: "Ctrl+Shift+C", run: copyImage },
    ] },
    { label: "View", items: [
      { heading: "Look" },
      ...THEMES.map(([key, title]) => ({ label: title, checked: () => currentTheme === key, run: () => setTheme(key) })),
    ] },
    { label: "Help", items: [
      { label: `About ${options.app.name}…`, run: showAbout },
      { label: "Report an issue…", run: () => openLink(options.app.issues_url) },
    ] },
  ]);
  status("");
  await refresh();
  // For tests: the label as the page sees it, and whether it is idle.
  window.__dotlab = { client: "web", engine, spec, form, refresh, idle: () => !rendering, pixels: () => last };
}

function fill(select, values) {
  for (const value of values) select.append(new Option(value, value));
}

main().catch((e) => status(e.message || String(e), true));
