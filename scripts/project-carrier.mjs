// Project med-autocast's domain resources into its native plugin carrier via Framework CLI.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function resolveOplBin() {
  const envBin = process.env.OPL_BIN?.trim();
  if (envBin) return envBin;
  const fwRoot = process.env.OPL_FRAMEWORK_ROOT?.trim();
  if (fwRoot) {
    const candidate = path.join(fwRoot, 'bin', 'opl');
    if (fs.existsSync(candidate)) return candidate;
  }
  const sibling = path.resolve(root, '..', 'one-person-lab', 'bin', 'opl');
  if (fs.existsSync(sibling)) return sibling;
  return 'opl';
}

const args = ['pack', 'project-carrier', '--repo', root, '--json'];
if (process.argv.includes('--check')) {
  args.push('--check');
}

const result = spawnSync(resolveOplBin(), args, { stdio: 'inherit' });
if (result.error) {
  throw result.error;
}
process.exit(result.status ?? 1);
