// Renders labels in Pyodide (the browser's engine) and writes their hashes, for tests/test_web_parity.py to compare with
// the native engine's. Not a node:test file on purpose (it needs Pyodide and the network).
//   node parity.mjs CASES.json OUT.json SRC_DOTLAB_DIR PYODIDE_DIR   (PYODIDE_DIR has node_modules/pyodide in it)
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [casesPath, outPath, packageDir, pyodideDir] = process.argv.slice(2);
const { loadPyodide } = await import(pathToFileURL(path.join(pyodideDir, "node_modules", "pyodide", "pyodide.mjs")));
const py = await loadPyodide();
await py.loadPackage(["Pillow", "fonttools", "micropip"]);
await py.runPythonAsync(`import micropip\nawait micropip.install("qrcode==8.2")`); // the version the site ships
py.FS.mkdirTree("/pkg/dotlab");
py.mountNodeFS("/pkg/dotlab", packageDir);
py.runPython("import sys; sys.path.insert(0, '/pkg')");
py.globals.set("cases_json", fs.readFileSync(casesPath, "utf8"));
const hashes = await py.runPythonAsync(`
import hashlib, json
from dotlab import api
cases = json.loads(cases_json)
json.dumps({name: hashlib.sha256(api.preview_pixels(spec)).hexdigest()[:16] for name, spec in cases.items()})
`);
fs.writeFileSync(outPath, hashes);
