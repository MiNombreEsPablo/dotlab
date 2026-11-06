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
import { createLayersWidget, hasContent as layersHaveContent, withoutPictures } from "./layers.js";
import { createMenubar } from "./menus.js";
import { previewFonts } from "./fontpreview.js";
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
  // The label being designed is remembered between visits, so a reload or a closed tab loses nothing. Its picture is not
  // (it lives in the engine's memory, not in storage): the page says so when it restores a label that had one.
  let saveTimer = null;
  const rememberNow = () => {
    clearTimeout(saveTimer);
    saveTimer = null; // nothing pending any more
    const current = spec();
    const { text, had } = withoutPictures(current.layers);
    store.set("label", { spec: { ...current, layers: text }, hadPicture: had });
  };
  const remember = () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(rememberNow, 500);
  };
  addEventListener("pagehide", () => { if (saveTimer) rememberNow(); });

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
        remember();
        if (activeTab === "doodle") doodle.setUnderlay(pixels);
        $("hint").textContent = hints.join(" ");
        $("hint").hidden = hints.length === 0;
        $("empty").hidden = activeTab === "doodle" || hasContent(spec());
      } while (again);
      if ($("status").classList.contains("error")) status("");
    } catch (e) {
      status(`Couldn't draw the label: ${e.message}`, true);
    } finally {
      rendering = false;
    }
  }

  // a picture the user chose, dropped or pasted: the engine takes it in and hands back the path the label uses
  async function useFile(file, replace = false) {
    if (!file) return;
    status(`Reading ${file.name}…`);
    const started = performance.now();
    try {
      const path = await engine.addImage(new Uint8Array(await file.arrayBuffer()), file.name);
      if (!layersUi.usePicture(path, file.name, replace)) return; // (the label is full: the widget said so)
      status("");
      await refresh();
      const seconds = (performance.now() - started) / 1000;
      if (seconds > 1.5) status(`${file.name} (${(file.size / 1e6).toFixed(1)} MB) took ${seconds.toFixed(1)} s to load.`);
    } catch (e) {
      status(`Couldn't use that picture: ${e.message}`, true);
    }
  }
  const picture = createImageWidget(useFile, (text) => status(text, true));
  const layersUi = createLayersWidget(options, { image: picture.make, fonts: (select) => previewFonts(select, options.fonts), say: status, paper: () => form.read() });
  const doodle = createDoodleWidget(options);
  document.querySelector(".paper").append(layersUi.overlay, doodle.overlay);
  let activeTab = "";
  const form = buildForm(options.form, options.defaults, (field) => {
    if (field.tab === "output") return; // copies and darkness don't change the picture
    if (field.name === "border_style" || field.name === "bars") layersUi.paperChanged();
    if (field.name === "doodle" && activeTab === "doodle") { // the overlay already shows what was drawn
      remember();
      return;
    }
    refresh();
  }, { layers: layersUi.make, doodle: doodle.make }, (id) => {
    const wasDrawing = activeTab === "doodle";
    activeTab = id;
    doodle.setActive(id === "doodle");
    layersUi.setActive(id === "layers");
    if (wasDrawing || id === "doodle") refresh(); // the doodle moves between the engine's picture and the overlay
  });
  layersUi.setPaper(form.paper);

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
  function writeForm(label) { // every way a whole label arrives (preset, file, last visit, new): the layers learn where the frame is
    form.write(label);
    layersUi.syncPaper();
  }
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

  const hasContent = (label) => // as spec.has_content
    options.content_fields.some((name) => name !== "layers" && String(label[name] ?? "").trim()) || layersHaveContent(label.layers);

  // saving and copying the label as an image: the engine renders the PNG, the files seam delivers it
  for (const [scale, name] of options.export.scales) $("export-size").append(new Option(name, scale));
  $("export-size").value = await store.get("exportScale", options.export.scales[0][0]);
  $("export-size").addEventListener("input", () => store.set("exportScale", Number($("export-size").value)));
  async function makeImage(doing) { // (for the clipboard: Save keeps the editable label file)
    const current = spec();
    if (!hasContent(current)) {
      status(`Nothing to ${doing}.`);
      return null;
    }
    return engine.exportPng(current, Number($("export-size").value));
  }
  async function copyImage() {
    try {
      const image = await makeImage("copy");
      if (!image) return;
      await files.copyImage(image.data);
      status("Copied. Paste it anywhere.");
    } catch (e) {
      status(`Couldn't copy the image: ${e.message}`, true);
    }
  }
  $("copy-image").addEventListener("click", copyImage);

  // presets: named styles (the label without its picture); choosing one replaces the label
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
    try {
      writeForm(await engine.migrate(loaded)); // (a preset kept before layers has none)
    } catch (e) {
      return status(`Couldn't open the preset “${name}”: ${e.message}`, true);
    }
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
      status(`Saved preset “${saved}”.${withoutPictures(spec().layers).had ? " (A preset keeps the style, not the picture: Save… keeps both.)" : ""}`);
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
      writeForm(await engine.compositionLoads(new Uint8Array(await file.arrayBuffer())));
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
        writeForm(label);
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
    else status(result.problems.length ? `Printer: ${result.problems.join(", ")}` : "Sent. Your sticker is on its way.");
  }
  $("print").addEventListener("click", print);
  $("print").disabled = false;

  async function newLabel() {
    if (hasContent(spec()) && !confirm("Start a new label? The current one is replaced: use Save first to keep it.")) return;
    writeForm({}); // every control back to its default: one empty text layer, no doodle
    $("preset").value = "";
    resetDelete();
    await refresh();
    status("New label.");
  }

  // the menu bar: every item calls an action the buttons already use
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
      { label: "New label", run: newLabel },  // (no shortcut: browsers keep Ctrl+N for a new window)
      { label: "Open label…", shortcut: "Ctrl+O", run: () => $("label-file").click() },
      { label: "Save…", shortcut: "Ctrl+S", run: saveLabel },  // a PNG any viewer opens, which Dotlab can also reopen and edit
      "-",
      { label: "Print", shortcut: "Ctrl+P", run: print, enabled: () => !$("print").disabled },
    ] },
    { label: "Edit", items: [
      { label: "Paste image", shortcut: "Ctrl+V", display: true, run: () => picture.paste() },
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
  const kept = await store.get("label", null);
  let restoreNote = "";
  if (kept && kept.spec) {
    try {
      writeForm(await engine.migrate(kept.spec));
      if (kept.hadPicture) status("Restored your last label. Its picture isn't kept: add it again, or use Save, which keeps pictures.");
    } catch (e) { // a label that can't be opened: start fresh, and say why
      restoreNote = `Couldn't restore your last label (${e.message}); starting a new one.`;
    }
  }
  await refresh();
  if (restoreNote) status(restoreNote, true);
  // For tests: the label as the page sees it, and whether it is idle.
  window.__dotlab = { client: "web", engine, spec, form, refresh, idle: () => !rendering, pixels: () => last };
}

function fill(select, values) {
  for (const value of values) select.append(new Option(value, value));
}

main().catch((e) => status(e.message || String(e), true));
