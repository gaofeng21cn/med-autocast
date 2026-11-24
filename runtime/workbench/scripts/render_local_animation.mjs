// Shared deterministic Remotion (@remotion/renderer) -> H.264/AAC runner.
// Supports both native `remotion_dom` entries and `window.__seek(t)` HTML projects
// while preserving master-clock audio timing and review receipts.
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { once } from 'node:events';
import fs from 'node:fs/promises';
import { createServer } from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { bundle, renderMedia, resolveBrowserExecutable, selectComposition } from './remotion_runtime.mjs';
import { collectRuntimeReceipt } from './runtime_receipt.mjs';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const config = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
const project = path.resolve(config.project_root);
const target = path.resolve(config.output);
const fps = Number(config.fps || 24);
const width = Number(config.width || 1280);
const height = Number(config.height || 720);
if (
  ![fps, width, height].every(Number.isInteger) ||
  fps < 1 ||
  fps > 60 ||
  width < 64 ||
  height < 64 ||
  width % 2 ||
  height % 2
) {
  throw Error('帧率或画布尺寸无效（宽高须为偶数）');
}

const voice = path.resolve(config.audio);
const probe = JSON.parse(
  execFileSync('ffprobe', ['-v', 'error', '-show_format', '-show_streams', '-of', 'json', voice], {
    encoding: 'utf8',
  }),
);
const audioStream = probe.streams.find((s) => s.codec_type === 'audio');
if (!audioStream) throw Error('旁白没有音频流');
// Retained AAC mixes already match MP4: preserve their encoded packets.
const audioMode = audioStream.codec_name === 'aac' ? 'copy' : 'encode_aac';
const duration = Number(probe.format.duration);
if (!(duration > 0) || !Number.isFinite(duration)) throw Error('旁白时长无效');
try {
  await fs.access(target);
  throw Error('目标已存在，请使用新修订输出路径');
} catch (e) {
  if (e.code !== 'ENOENT') throw e;
}

await fs.mkdir(path.dirname(target), { recursive: true });
const temp = await fs.mkdtemp(path.join(path.dirname(target), '.render-'));
const entry = config.entry || 'index.html';
const retainFrames = config.retain_render_frames === true;
const frames = Math.max(1, Math.ceil(duration * fps));
const browserExecutable = resolveBrowserExecutable();

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.css': 'text/css; charset=utf-8',
  '.woff2': 'font/woff2',
  '.wav': 'audio/wav',
  '.flac': 'audio/flac',
  '.mp3': 'audio/mpeg',
  '.m4a': 'audio/mp4',
  '.map': 'application/json; charset=utf-8',
};

async function getSeekHostBundleDir() {
  const hostDir = path.join(scriptDir, 'remotion_seek_host');
  const indexPath = path.join(hostDir, 'index.tsx');
  const compPath = path.join(hostDir, 'SeekHostComposition.tsx');
  const hash = createHash('sha256')
    .update(await fs.readFile(indexPath))
    .update(await fs.readFile(compPath))
    .update(process.version)
    .digest('hex')
    .slice(0, 16);
  const cacheDir = path.join(os.tmpdir(), `med-autocast-remotion-seek-host-${hash}`);
  const readyMarker = path.join(cacheDir, 'index.html');
  try {
    await fs.access(readyMarker);
    return cacheDir;
  } catch {
    const staging = `${cacheDir}.tmp-${process.pid}-${Date.now()}`;
    await bundle({
      entryPoint: indexPath,
      outDir: staging,
      onProgress: () => {},
    });
    try {
      await fs.rename(staging, cacheDir);
    } catch {
      await fs.rm(staging, { recursive: true, force: true });
    }
    return cacheDir;
  }
}

async function readJsonBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

async function serveContained(rootReal, rawSubpath, res, onError) {
  const cleanSubpath = rawSubpath.replace(/^\/+/, '') || 'index.html';
  try {
    const candidate = path.resolve(rootReal, cleanSubpath);
    const file = await fs.realpath(candidate);
    const rel = path.relative(rootReal, file);
    if (rel.startsWith('..') || path.isAbsolute(rel)) {
      res.writeHead(403).end();
      return;
    }
    const stat = await fs.stat(file);
    const finalFile = stat.isDirectory() ? path.join(file, 'index.html') : file;
    res.setHeader('Content-Type', mime[path.extname(finalFile).toLowerCase()] || 'application/octet-stream');
    res.end(await fs.readFile(finalFile));
  } catch {
    if (onError && cleanSubpath !== 'favicon.ico') {
      onError(`资源 HTTP 404: /${cleanSubpath}`);
    }
    res.writeHead(404).end();
  }
}

let server;
const errors = [];
const frameTelemetry = new Map();
let rendererRuntime = { renderer_id: null, requested_style_id: null, style_id: null };

try {
  const videoOnly = path.join(temp, 'video-only.mp4');
  const finalTemp = path.join(temp, 'video.mp4');
  const concurrency = config.concurrency ?? (frames <= 48 ? 1 : undefined);
  const remotionEntry = config.remotion_entry ? path.resolve(project, config.remotion_entry) : null;

  if (remotionEntry) {
    const sharedNodeModules = [
      process.env.MED_AUTOCAST_REMOTION_ROOT && path.join(process.env.MED_AUTOCAST_REMOTION_ROOT, 'node_modules'),
      process.env.MED_AUTOCAST_WORKSPACE_ROOT && path.join(process.env.MED_AUTOCAST_WORKSPACE_ROOT, 'node_modules'),
      path.resolve(scriptDir, '..', 'node_modules'),
    ].filter(Boolean);
    const bundleDir = path.join(temp, 'remotion-entry-bundle');
    const serveUrl = await bundle({
      entryPoint: remotionEntry,
      outDir: bundleDir,
      onProgress: () => {},
      webpackOverride: (cfg) => ({
        ...cfg,
        resolve: {
          ...cfg.resolve,
          modules: [...(cfg.resolve?.modules || ['node_modules']), ...sharedNodeModules],
        },
      }),
    });
    const scorePath = path.join(project, 'score.json');
    let score = null;
    try {
      score = JSON.parse(await fs.readFile(scorePath, 'utf8'));
    } catch {
      score = null;
    }
    const inputProps = {
      ...(config.input_props || {}),
      ...(score ? { score } : {}),
      width,
      height,
    };
    const compositionId = config.composition_id || 'PaperTheatre';
    const composition = await selectComposition({
      serveUrl,
      id: compositionId,
      inputProps,
      browserExecutable,
    });
    await renderMedia({
      composition: {
        ...composition,
        fps,
        width,
        height,
        durationInFrames: frames,
      },
      serveUrl,
      codec: 'h264',
      crf: 18,
      pixelFormat: 'yuv420p',
      muted: true,
      outputLocation: videoOnly,
      inputProps,
      browserExecutable,
      concurrency,
      chromiumOptions: { disableWebSecurity: false },
    });
    rendererRuntime = {
      renderer_id: 'remotion_dom',
      requested_style_id: score?.style?.styleId || null,
      style_id: score?.style?.appliedStyleId || score?.style?.styleId || null,
    };
    if (score?.shots?.length) {
      for (const shot of score.shots) {
        frameTelemetry.set(Math.round(Number(shot.start || 0) * fps), {
          shot: shot.id || null,
          renderer_id: 'remotion_dom',
          style_id: shot.styleId || rendererRuntime.style_id,
          start: Number(shot.start || 0),
        });
      }
    }
  } else {
    const bundleDir = await getSeekHostBundleDir();
    const bundleReal = await fs.realpath(bundleDir);
    const projectReal = await fs.realpath(project);

    server = createServer(async (req, res) => {
      const url = new URL(req.url || '/', 'http://127.0.0.1');
      const pathname = decodeURIComponent(url.pathname);
      if (req.method === 'POST' && pathname === '/__telemetry') {
        try {
          const body = await readJsonBody(req);
          if (body.kind === 'runtime') {
            rendererRuntime = {
              renderer_id: body.renderer_id ?? null,
              requested_style_id: body.requested_style_id ?? null,
              style_id: body.style_id ?? null,
            };
          } else if (body.kind === 'frame' && Number.isInteger(body.frame)) {
            frameTelemetry.set(body.frame, {
              shot: body.shot ?? null,
              renderer_id: body.renderer_id ?? null,
              style_id: body.style_id ?? null,
              start: Number(body.time ?? body.frame / fps),
            });
          } else if (body.kind === 'error' && body.message) {
            errors.push(String(body.message));
          }
          res.writeHead(204).end();
        } catch {
          res.writeHead(400).end();
        }
        return;
      }
      if (pathname === '/__project' || pathname.startsWith('/__project/')) {
        const sub = pathname.slice('/__project'.length);
        await serveContained(projectReal, sub, res, (msg) => errors.push(msg));
        return;
      }
      await serveContained(bundleReal, pathname, res, null);
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const serveUrl = `http://127.0.0.1:${server.address().port}`;
    const inputProps = { entry, width, height, fps, durationInFrames: frames };
    const composition = await selectComposition({
      serveUrl,
      id: 'SeekHost',
      inputProps,
      browserExecutable,
    });
    await renderMedia({
      composition,
      serveUrl,
      codec: 'h264',
      crf: 18,
      pixelFormat: 'yuv420p',
      muted: true,
      outputLocation: videoOnly,
      inputProps,
      browserExecutable,
      concurrency,
    });
  }

  if (errors.length) throw Error(errors.join('\n'));

  const audioArgs = audioMode === 'copy' ? ['-c:a', 'copy'] : ['-c:a', 'aac', '-b:a', '192k'];
  execFileSync('ffmpeg', [
    '-v', 'error', '-y',
    '-i', videoOnly,
    '-i', voice,
    '-map', '0:v:0',
    '-map', '1:a:0',
    '-t', String(duration),
    '-c:v', 'copy',
    ...audioArgs,
    '-movflags', '+faststart',
    finalTemp,
  ]);
  execFileSync('ffmpeg', ['-v', 'error', '-i', finalTemp, '-f', 'null', '-']);

  if (retainFrames) {
    const sampleFrames = [...new Set([0, Math.floor(frames / 2), frames - 1])];
    for (const frameIndex of sampleFrames) {
      execFileSync('ffmpeg', [
        '-v', 'error', '-y',
        '-ss', (frameIndex / fps).toFixed(6),
        '-i', finalTemp,
        '-frames:v', '1',
        path.join(temp, `frame-${frameIndex}.png`),
      ]);
    }
  }

  // Hard-link publishes only a completed file and never overwrites another revision.
  await fs.link(finalTemp, target);
  await fs.unlink(finalTemp);
  await fs.rm(videoOnly, { force: true });

  const styleSequence = [];
  for (const frameIndex of [...frameTelemetry.keys()].sort((a, b) => a - b)) {
    const identity = frameTelemetry.get(frameIndex);
    const last = styleSequence.at(-1);
    if (
      !last ||
      last.shot !== identity.shot ||
      last.style_id !== identity.style_id ||
      last.renderer_id !== identity.renderer_id
    ) {
      styleSequence.push({
        shot: identity.shot,
        renderer_id: identity.renderer_id,
        style_id: identity.style_id,
        start: identity.start,
      });
    }
  }

  const runtimeReceipt = await collectRuntimeReceipt({
    project,
    entry: remotionEntry ? config.remotion_entry : entry,
    audio: voice,
    config: { fps, width, height, engine: '@remotion/renderer' },
  });
  const receipt = {
    status: 'rendered',
    output: target,
    frames,
    duration,
    fps,
    width,
    height,
    render_engine: '@remotion/renderer',
    audio_encoding: { source_codec: audioStream.codec_name, mode: audioMode },
    evidence_directory: retainFrames ? temp : null,
    storage_profile: {
      render_scratch: retainFrames ? 'retained_diagnostics' : 'temporary',
      policy: 'necessity_first',
    },
    renderer_runtime: rendererRuntime,
    style_sequence: styleSequence,
    runtime_receipt: runtimeReceipt,
    release_eligible: false,
  };
  await fs.writeFile(`${target}.runtime.json`, `${JSON.stringify(receipt, null, 2)}\n`);
  console.log(JSON.stringify(receipt));
} finally {
  if (server) server.close();
  if (!retainFrames) await fs.rm(temp, { recursive: true, force: true });
}
