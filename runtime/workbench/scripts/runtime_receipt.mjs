import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import os from 'node:os';
import path from 'node:path';
import { browserLaunchOptions } from './playwright_runtime.mjs';

function toolVersion(name, args = ['-version']) {
  try {
    return execFileSync(name, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim().split('\n')[0];
  } catch (error) {
    return `unavailable: ${error?.message || String(error)}`;
  }
}

async function fileSha256(file) {
  try {
    const bytes = await readFile(file);
    return createHash('sha256').update(bytes).digest('hex');
  } catch {
    return null;
  }
}

export async function collectRuntimeReceipt({ project, entry = 'index.html', audio = null, config = {} } = {}) {
  const root = path.resolve(project);
  const candidates = [
    ['entry', path.resolve(root, entry)],
    ['project', path.join(root, 'project.json')],
    ['score', path.join(root, 'score.json')],
    ['bundle', path.join(root, 'dist', 'film.js')],
  ];
  if (audio) candidates.push(['audio', path.resolve(audio)]);
  const inputs = {};
  for (const [name, file] of candidates) {
    const sha256 = await fileSha256(file);
    if (sha256) inputs[name] = { path: file, sha256 };
  }
  return {
    schema: 'medical_animation_runtime_receipt/v1',
    captured_at: new Date().toISOString(),
    host: { platform: process.platform, arch: process.arch, node: process.version, os: os.release() },
    browser: { executable: browserLaunchOptions.executablePath || process.env.CHROME_PATH || null },
    tools: { ffmpeg: toolVersion('ffmpeg'), ffprobe: toolVersion('ffprobe') },
    inputs,
    contract: {
      seek_api: 'window.__seek(t_seconds)',
      random_access_required: true,
      master_clock: 'score.json',
      frame_capture: 'Chrome screenshot -> FFmpeg',
      config: { fps: config.fps ?? null, width: config.width ?? null, height: config.height ?? null },
    },
  };
}
