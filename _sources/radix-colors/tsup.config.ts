/// <reference types="node" />
import { defineConfig, type Options } from "tsup";

const LOUD = process.env.LOUD === "true";

const options: Options = {
  entry: ["src/index.ts"],
  outDir: "dist",
  clean: true,
  dts: true,
  sourcemap: true,
  silent: !LOUD,
  tsconfig: "./tsconfig.package.json",
};

export default defineConfig([
  { ...options, format: "esm", outExtension: () => ({ js: ".mjs" }) },
  { ...options, format: "cjs" },
]);
