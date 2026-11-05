// Files seam, browser adapter: a file the page made is offered as a download; an image goes to the clipboard through the
// browser's own clipboard.   save(bytes, name, mime, kind) -> {saved, cancelled?, error?}   copyImage(pngBytes) -> void (throws)
// (`kind` words the file type in a dialog, "PNG image"; a download has no dialog)

export async function copyImage(bytes) {
  if (!navigator.clipboard || !window.ClipboardItem) {
    throw new Error("This browser can't copy images to the clipboard: use Save instead.");
  }
  try {
    await navigator.clipboard.write([new ClipboardItem({ "image/png": new Blob([bytes], { type: "image/png" }) })]);
  } catch (e) {
    throw new Error(e.name === "NotAllowedError" ? "The browser didn't allow copying: click the page and try again." : e.message);
  }
}

export function createFiles() {
  return {
    openLink(url) { // one of the project's pages, in a new tab
      window.open(url, "_blank", "noopener");
    },
    async save(bytes, name, mime, kind) {
      const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
      const link = Object.assign(document.createElement("a"), { href: url, download: name });
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      return { saved: name };
    },
    copyImage,
  };
}
