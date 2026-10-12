import { build } from "esbuild";
import { mkdir } from "node:fs/promises";

// The default entry stays the three-sample viewer. Any additional example is
// built the same way so every published action sample runs the real runtime.
const entries = [
  { name: "film", entry: "src/main.ts", outdir: "dist" },
  { name: "action_gallery", entry: "examples/action_gallery/main.ts", outdir: "examples/action_gallery/dist" },
];

for (const { name, entry, outdir } of entries) {
  await mkdir(outdir, { recursive: true });
  await build({
    entryPoints: [entry],
    bundle: true,
    format: "iife",
    target: "es2022",
    outfile: `${outdir}/film.js`,
    sourcemap: true,
    ...(name === "film" ? {} : { define: { __GALLERY__: "true" } }),
  });
}
