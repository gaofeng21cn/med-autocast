// Explicit bridge for animation projects without project-level node_modules.
import {createRequire} from 'node:module';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = process.env.MED_AUTOCAST_WORKSPACE_ROOT || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'package.json'));
let runtime;
try {
  runtime = require('playwright');
} catch (error) {
  const shared = process.env.MED_AUTOCAST_PLAYWRIGHT_ROOT;
  if (shared) {
    runtime = createRequire(path.join(shared, 'package.json'))('playwright');
  } else {
    throw new Error(`工作区缺少 Playwright，请为该工作区安装依赖或设置 MED_AUTOCAST_PLAYWRIGHT_ROOT 指向已安装的本机运行时`, {cause:error});
  }
}
export const chromium = runtime.chromium;
export const browserLaunchOptions = {headless:true, ...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {})};
