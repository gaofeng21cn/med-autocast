// Explicit bridge for @remotion/bundler and @remotion/renderer without requiring project-level node_modules.
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const searchRoots = [
  process.env.MED_AUTOCAST_REMOTION_ROOT,
  process.env.MED_AUTOCAST_WORKSPACE_ROOT,
  path.resolve(scriptDir, '..'),
].filter(Boolean);

function requireFromRoots(pkgName) {
  let lastError;
  for (const root of searchRoots) {
    try {
      const req = createRequire(path.join(root, 'package.json'));
      return req(pkgName);
    } catch (error) {
      lastError = error;
    }
  }
  throw new Error(
    `工作区缺少 ${pkgName}，请在 runtime/workbench 运行 npm ci 或设置 MED_AUTOCAST_WORKSPACE_ROOT / MED_AUTOCAST_REMOTION_ROOT`,
    { cause: lastError },
  );
}

export const { bundle } = requireFromRoots('@remotion/bundler');
export const { selectComposition, renderMedia } = requireFromRoots('@remotion/renderer');

export function resolveBrowserExecutable() {
  if (process.env.CHROME_PATH && fs.existsSync(process.env.CHROME_PATH)) {
    return process.env.CHROME_PATH;
  }
  // Prefer an already-installed Playwright Chromium or local Chrome so offline
  // sandboxes and CI do not have to download a second browser binary.
  for (const root of searchRoots) {
    try {
      const pw = createRequire(path.join(root, 'package.json'))('playwright');
      const exe = pw?.chromium?.executablePath?.();
      if (exe && fs.existsSync(exe)) return exe;
    } catch {
      // Optional Playwright fallback; continue checking system Chrome paths.
    }
  }
  const systemCandidates = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ];
  for (const candidate of systemCandidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return undefined;
}
