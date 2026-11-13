// Used by start.cmd: exits 1 if a package named in package.json is not installed, or an exactly pinned one is at
// another version, so that npm install runs only when it is needed. Offline, and well under a second.
import { existsSync, readFileSync } from "node:fs";

const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const wanted = { ...read("./package.json").dependencies, ...read("./package.json").devDependencies };
const stale = Object.entries(wanted).filter(([name, spec]) => {
  const installed = new URL(`./node_modules/${name}/package.json`, import.meta.url);
  if (!existsSync(installed)) return true;
  return /^\d+\.\d+\.\d+$/.test(spec) && read(installed.href).version !== spec;
});
if (stale.length) {
  console.log(`Missing or out of date: ${stale.map(([name]) => name).join(", ")}`);
  process.exit(1);
}
