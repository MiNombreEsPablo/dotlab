// The looks (their values are in themes.css). Choosing one sets data-theme on <html>; the page reads a few tokens back
// (the preview's tint) because the canvas can't use CSS.

export const THEMES = [
  ["y2k-blue", "Y2K Blue"],
  ["y2k-pink", "Y2K Pink"],
  ["gunmetal", "Gunmetal"],
  ["handheld", "Handheld"],
  ["system", "System"],
];
export const DEFAULT_THEME = THEMES[0][0];

export function applyTheme(key) { // anything unknown (an old saved value) falls back to the default
  const known = THEMES.some(([k]) => k === key);
  document.documentElement.dataset.theme = known ? key : DEFAULT_THEME;
  return known ? key : DEFAULT_THEME;
}

const probe = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
function rgb(css, fallback) { // any CSS colour -> [r, g, b]
  probe.clearRect(0, 0, 1, 1);
  probe.fillStyle = "#000";
  probe.fillStyle = css.trim() || fallback;
  probe.fillRect(0, 0, 1, 1);
  return Array.from(probe.getImageData(0, 0, 1, 1).data.slice(0, 3));
}

// What the preview's black and white dots are drawn in (black and white, except in the looks that tint the screen).
export function previewColors() {
  const style = getComputedStyle(document.documentElement);
  return { ink: rgb(style.getPropertyValue("--preview-ink"), "#000"), paper: rgb(style.getPropertyValue("--preview-paper"), "#fff") };
}
