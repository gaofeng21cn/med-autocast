import { build } from "esbuild";
await build({
  entryPoints: ["src/main.ts"],
  bundle: true,
  format: "iife",
  target: "es2022",
  outfile: "dist/film.js",
  sourcemap: true,
});
