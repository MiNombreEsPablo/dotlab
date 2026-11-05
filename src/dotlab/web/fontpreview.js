// Shows each font's name in its own face inside the Font dropdown's list.
//   previewFonts(select, options.fonts)
// The faces are declared only when the dropdown is first touched: the Japanese ones are 2-3 MB each, and a visitor who
// never opens the list shouldn't pay for them (the service worker keeps them afterwards). A browser that draws its
// own list (macOS and iOS) ignores the styling; the names are then plain, as before.

export function previewFonts(select, fonts) {
  const name = (family) => `Dotlab preview ${family}`;
  const css = (family) => `"${name(family)}", sans-serif`;
  const known = new Set(fonts.map((f) => f.family));
  for (const option of select.options) if (known.has(option.value)) option.style.fontFamily = css(option.value);

  let declared = false;
  const declare = () => {
    if (declared) return;
    declared = true;
    const style = document.createElement("style");
    style.textContent = fonts.map((f) => {
      const file = f.files.regular || Object.values(f.files)[0];
      return `@font-face { font-family: "${name(f.family)}"; src: url("fonts/${encodeURIComponent(file)}") format("truetype"); font-weight: 100 900; font-display: swap; }`;
    }).join("\n");
    document.head.append(style);
  };
  for (const type of ["pointerdown", "focus", "keydown"]) select.addEventListener(type, declare, { once: true });
}
