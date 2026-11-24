// Project med-autocast's domain resources into its native plugin carrier.
// Prefers Framework CLI (`opl pack project-carrier`), with a deterministic
// standalone projector fallback driven by contracts/carrier_projection.json
// so fresh checkouts and standalone CI can materialize the gitignored carrier.
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const checkOnly = process.argv.includes('--check');

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

function tryFrameworkProjector() {
  const args = ['pack', 'project-carrier', '--repo', root, '--json'];
  if (checkOnly) args.push('--check');
  const result = spawnSync(resolveOplBin(), args, { encoding: 'utf8' });
  if (result.error) return null;
  const stdout = (result.stdout || '').trim();
  const stderr = (result.stderr || '').trim();
  // Fall back only when the external OPL CLI itself is unavailable or lacks its
  // own node_modules; real drift/contract errors must surface directly.
  if (
    result.status !== 0 &&
    !stdout.includes('"opl_carrier_projection"') &&
    (stderr.includes('ERR_MODULE_NOT_FOUND') || stderr.includes('Cannot find package') || result.status === 127)
  ) {
    return null;
  }
  if (stdout) process.stdout.write(`${stdout}\n`);
  if (stderr) process.stderr.write(`${stderr}\n`);
  return result.status ?? 1;
}

function jsonBytes(payload) {
  return Buffer.from(`${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function joinRel(...parts) {
  return parts
    .filter((p) => typeof p === 'string' && p.trim().length > 0)
    .map((p) => p.replace(/^\/+|\/+$/g, ''))
    .filter(Boolean)
    .join('/');
}

function walkResources(repoRoot, rootRel, excludeSegments, out) {
  const startDir = path.join(repoRoot, rootRel);
  if (!fs.existsSync(startDir) || fs.lstatSync(startDir).isSymbolicLink() || !fs.lstatSync(startDir).isDirectory()) {
    return;
  }
  const visit = (dirAbs, relPrefix) => {
    const entries = fs.readdirSync(dirAbs, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      if (entry.isSymbolicLink() || entry.name === '.git') continue;
      if (excludeSegments.has(entry.name)) continue;
      const childRel = `${relPrefix}/${entry.name}`;
      if (entry.isDirectory()) {
        visit(path.join(dirAbs, entry.name), childRel);
      } else if (entry.isFile()) {
        out.push(childRel);
      }
    }
  };
  visit(startDir, rootRel);
}

function updatePluginManifest(repoRoot, rule, owner) {
  const existing = JSON.parse(fs.readFileSync(path.join(repoRoot, rule.path), 'utf8'));
  const updated = structuredClone(existing);
  if (rule.sync_version) updated.version = owner.version;
  if (rule.sync_name_from_plugin_id && owner.codex_surface?.plugin_id) {
    updated.name = owner.codex_surface.plugin_id;
  }
  if (rule.set_fields) Object.assign(updated, structuredClone(rule.set_fields));
  if (rule.sync_interface) {
    const iconRef = owner.presentation?.icon_ref;
    const prefix = rule.sync_interface.logo_prefix ?? './';
    const iconPath = typeof iconRef === 'string' && iconRef ? `${prefix}${iconRef.replace(/^\.\//, '')}` : undefined;
    let uiTarget;
    if (rule.sync_interface.target_pointer === 'interface') {
      updated.interface = updated.interface || {};
      uiTarget = updated.interface;
    } else {
      updated.extensions = updated.extensions || {};
      updated.extensions['com.openai'] = updated.extensions['com.openai'] || {};
      updated.extensions['com.openai'].interface = updated.extensions['com.openai'].interface || {};
      uiTarget = updated.extensions['com.openai'].interface;
    }
    if (typeof owner.display_name === 'string') uiTarget.displayName = owner.display_name;
    if (iconPath) {
      uiTarget.logo = iconPath;
      uiTarget.composerIcon = iconPath;
    }
  }
  return jsonBytes(updated);
}

function rewriteAdapter(repoRoot, cfg) {
  const parsed = JSON.parse(fs.readFileSync(path.join(repoRoot, cfg.source), 'utf8'));
  const cloned = structuredClone(parsed);
  const rewrites = new Map((cfg.argv_rewrites || []).map((item) => [item.from, item.to]));
  for (const section of ['reads', 'actions']) {
    const map = cloned[section];
    if (!map || typeof map !== 'object') continue;
    for (const entry of Object.values(map)) {
      if (entry && Array.isArray(entry.argv)) {
        entry.argv = entry.argv.map((arg) => (typeof arg === 'string' && rewrites.has(arg) ? rewrites.get(arg) : arg));
      }
    }
  }
  return jsonBytes(cloned);
}

function runStandaloneProjector() {
  const configRel = 'contracts/carrier_projection.json';
  const config = JSON.parse(fs.readFileSync(path.join(root, configRel), 'utf8'));
  const owner = JSON.parse(fs.readFileSync(path.join(root, 'contracts/opl_agent_package_manifest.json'), 'utf8'));
  const carrierRel = config.carrier_root.replace(/\/+$/, '');
  const targetPrefix = (config.resource_target_prefix || '').replace(/^\/+|\/+$/g, '');
  const excludeSegments = new Set(config.exclude_path_segments || []);

  const expected = new Map();
  const collected = [];
  for (const resourceRoot of config.resource_roots || []) {
    walkResources(root, resourceRoot, excludeSegments, collected);
  }
  for (const rel of collected) {
    expected.set(joinRel(carrierRel, targetPrefix, rel), fs.readFileSync(path.join(root, rel)));
  }
  for (const alias of config.file_aliases || []) {
    const src = path.join(root, alias.from);
    if (alias.optional && !fs.existsSync(src)) continue;
    expected.set(joinRel(carrierRel, alias.to), fs.readFileSync(src));
  }
  if (config.copy_presentation_icon && owner.presentation?.icon_ref) {
    const iconRel = owner.presentation.icon_ref.replace(/^\/+/, '');
    expected.set(joinRel(carrierRel, iconRel), fs.readFileSync(path.join(root, iconRel)));
  }
  if (config.adapter_projection) {
    expected.set(
      joinRel(carrierRel, config.adapter_projection.target),
      rewriteAdapter(root, config.adapter_projection),
    );
  }
  if (config.package_manifest_projection?.mode === 'clone_with_plugin_source_dot') {
    const cloned = structuredClone(owner);
    cloned.codex_surface = { ...(cloned.codex_surface || {}), plugin_source_path: '.' };
    expected.set(
      joinRel(carrierRel, config.package_manifest_projection.target || 'opl-package.json'),
      jsonBytes(cloned),
    );
  }
  for (const manifestRule of config.plugin_manifests || []) {
    expected.set(manifestRule.path, updatePluginManifest(root, manifestRule, owner));
  }

  const unexpectedFiles = [];
  for (const pruneSub of config.prune_roots || []) {
    const pruneAbs = path.join(root, joinRel(carrierRel, pruneSub));
    if (!fs.existsSync(pruneAbs)) continue;
    const scan = (dirAbs) => {
      for (const entry of fs.readdirSync(dirAbs, { withFileTypes: true })) {
        const abs = path.join(dirAbs, entry.name);
        const rel = path.relative(root, abs).replaceAll(path.sep, '/');
        if (entry.isSymbolicLink()) {
          unexpectedFiles.push(rel);
        } else if (entry.isDirectory()) {
          scan(abs);
        } else if (entry.isFile() && !expected.has(rel)) {
          unexpectedFiles.push(rel);
        }
      }
    };
    scan(pruneAbs);
  }
  unexpectedFiles.sort();

  const missingFiles = [];
  const driftedFiles = [];
  const writtenFiles = [];
  let unchangedCount = 0;

  for (const [targetRel, bytes] of [...expected.entries()].sort(([a], [b]) => a.localeCompare(b))) {
    const targetAbs = path.join(root, targetRel);
    if (!fs.existsSync(targetAbs)) {
      missingFiles.push(targetRel);
      if (!checkOnly) {
        fs.mkdirSync(path.dirname(targetAbs), { recursive: true });
        fs.writeFileSync(targetAbs, bytes);
        writtenFiles.push(targetRel);
      }
      continue;
    }
    if (fs.readFileSync(targetAbs).equals(bytes)) {
      unchangedCount += 1;
      continue;
    }
    driftedFiles.push(targetRel);
    if (!checkOnly) {
      fs.writeFileSync(targetAbs, bytes);
      writtenFiles.push(targetRel);
    }
  }

  const removedFiles = [];
  if (!checkOnly) {
    for (const staleRel of unexpectedFiles) {
      fs.unlinkSync(path.join(root, staleRel));
      removedFiles.push(staleRel);
    }
  }

  const hasDrift = missingFiles.length > 0 || driftedFiles.length > 0 || unexpectedFiles.length > 0;
  const report = {
    surface_kind: 'opl_carrier_projection',
    schema_version: 'opl_carrier_projection.v1',
    projector: 'standalone_fallback',
    mode: checkOnly ? 'check' : 'write',
    status: checkOnly ? (hasDrift ? 'drifted' : 'passed') : 'projected',
    repo_root: root,
    carrier_root: carrierRel,
    projection_config_ref: configRel,
    projected_file_count: expected.size,
    unchanged_count: unchangedCount,
    written_files: writtenFiles,
    removed_files: removedFiles,
    missing_files: missingFiles,
    drifted_files: driftedFiles,
    unexpected_files: unexpectedFiles,
  };
  process.stdout.write(`${JSON.stringify({ version: 'g2', pack_carrier_projection: report }, null, 2)}\n`);
  return checkOnly && hasDrift ? 1 : 0;
}

const fwStatus = tryFrameworkProjector();
process.exit(fwStatus !== null ? fwStatus : runStandaloneProjector());
