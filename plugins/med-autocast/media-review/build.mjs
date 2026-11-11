import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(new URL('.', import.meta.url).pathname);
const ui = await build({
  entryPoints: [resolve(root, 'app.js')],
  bundle: true,
  format: 'esm',
  platform: 'browser',
  write: false,
  minify: true,
  legalComments: 'inline',
});
const script = ui.outputFiles[0].text.replace(/<\/script/gi, '<\\/script');
const template = await readFile(resolve(root, 'template.html'), 'utf8');
const css = await readFile(resolve(root, 'style.css'), 'utf8');
await writeFile(resolve(root, 'index.html'), template
  .replace('/* STYLE */', () => css)
  .replace('/* SCRIPT */', () => script));

await build({
  entryPoints: [resolve(root, 'server.mjs')],
  outfile: resolve(root, 'server.bundle.mjs'),
  bundle: true,
  external: ['opl-framework/*'],
  platform: 'node',
  format: 'esm',
  target: 'node20',
  minify: true,
  legalComments: 'inline',
});
