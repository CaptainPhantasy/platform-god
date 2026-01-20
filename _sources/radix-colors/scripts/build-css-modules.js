import fs from "node:fs";
import path from "node:path";
import tsconfig from "../tsconfig.package.json" with { type: "json" };
import * as allColorScales from "../dist/index.mjs";

const outputDir = path.resolve(
  import.meta.dirname,
  ".."
  // TODO: Un-comment this before the next major version bump
  // tsconfig.compilerOptions.outDir
);

const supportsP3AtRule = "@supports (color: color(display-p3 1 1 1))";
const matchesP3MediaRule = "@media (color-gamut: p3)";

Object.keys(allColorScales)
  .filter((key) => !key.includes("P3"))
  .forEach((key) => {
    let selector = ":root, .light, .light-theme";

    if (key === "blackA" || key === "whiteA") {
      selector = ":root";
    }

    if (key.includes("Dark")) {
      selector = ".dark, .dark-theme";
    }

    const srgbValues = Object.entries(allColorScales).find(
      ([name]) => name === key
    )?.[1];

    if (!srgbValues) {
      throw new Error(`No srgb values found for ${key}`);
    }

    const srgbCssProperties = Object.entries(srgbValues)
      .map(([name, value]) => [toCssCasing(name), value])
      .map(([name, value]) => `  --${name}: ${value};`)
      .join("\n");

    const srgbCssRule = `${selector} {\n${srgbCssProperties}\n}`;

    const p3Values = Object.entries(allColorScales).find(
      ([name]) => name === key + "P3" || name === key.replace(/.$/, "P3A")
    )?.[1];

    if (!p3Values) {
      throw new Error(`No p3 values found for ${key}`);
    }

    const p3CssProperties = Object.entries(p3Values)
      .map(([name, value]) => [toCssCasing(name), value])
      .map(([name, value]) => `      --${name}: ${value};`)
      .join("\n");

    let p3CssRule = `    ${selector} {\n${p3CssProperties}\n    }`;
    p3CssRule = `  ${matchesP3MediaRule} {\n${p3CssRule}\n  }`;
    p3CssRule = `${supportsP3AtRule} {\n${p3CssRule}\n}`;

    fs.writeFileSync(
      path.join(outputDir, toFileName(key) + ".css"),
      `${srgbCssRule}\n\n${p3CssRule}`
    );
  });

/** @param {string} str */
function toCssCasing(str) {
  return str
    .replace(/([a-z])(\d)/, "$1-$2")
    .replace(/([A-Z])/g, "-$1")
    .toLowerCase();
}

/** @param {string} str */
function toFileName(str) {
  return toCssCasing(str).replace(/-a$/, "-alpha");
}
