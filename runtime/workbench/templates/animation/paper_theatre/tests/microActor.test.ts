import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function dependency(name: string) {
  for (const directory of [
    root,
    process.env.MED_AUTOCAST_WORKSPACE_ROOT,
    process.env.MED_AUTOCAST_WORKSPACE_ROOT &&
      path.join(process.env.MED_AUTOCAST_WORKSPACE_ROOT, "templates/animation/paper_theatre"),
    ...[1, 2, 3, 4, 5, 6].map((n) => path.resolve(root, ...Array(n).fill(".."))),
  ]) {
    if (!directory) continue;
    try {
      return createRequire(path.join(directory, "package.json"))(name);
    } catch (e) {
      if ((e as any).code !== "MODULE_NOT_FOUND") throw e;
    }
  }
}

async function loadMicroActorModule() {
  const esbuild = dependency("esbuild");
  if (!esbuild) return null;
  const bundle = await esbuild.build({
    entryPoints: [path.join(root, "src/kit/microActor.ts")],
    bundle: true,
    write: false,
    format: "cjs",
    platform: "neutral",
    mainFields: ["module", "main"],
    target: "es2022",
  });
  const mod = { exports: {} as Record<string, any> };
  const fn = new Function("exports", "module", bundle.outputFiles[0].text);
  fn(mod.exports, mod);
  return mod.exports;
}

function makeMockStage(images: Record<string, any> = {}) {
  const drawCalls: any[] = [];
  const boundsCalls: any[] = [];
  const clipRects: any[] = [];
  let state = { tx: 0, ty: 0, sx: 1, sy: 1, rot: 0, alpha: 1 };
  const stack: any[] = [];
  const g: any = {
    globalAlpha: 1,
    save: () => stack.push({ ...state, alpha: g.globalAlpha }),
    restore: () => {
      const prev = stack.pop();
      if (prev) {
        state = { tx: prev.tx, ty: prev.ty, sx: prev.sx, sy: prev.sy, rot: prev.rot };
        g.globalAlpha = prev.alpha;
      }
    },
    translate: (x: number, y: number) => {
      state.tx += x * state.sx;
      state.ty += y * state.sy;
    },
    rotate: (r: number) => {
      state.rot += r;
    },
    scale: (sx: number, sy: number) => {
      state.sx *= sx;
      state.sy *= sy;
    },
    beginPath: () => {},
    rect: (x: number, y: number, w: number, h: number) => {
      clipRects.push({ x, y, w, h });
    },
    ellipse: () => {},
    fill: () => {},
    drawImage: (im: any, ...args: number[]) => {
      drawCalls.push({ im, args, transform: { ...state } });
    },
  };
  const stage: any = {
    width: 1280,
    height: 720,
    tracking: true,
    g,
    assets: {},
    images,
    shadow: () => {},
    bounds: (rect: any) => {
      if (stage.tracking) boundsCalls.push(rect);
    },
    clip: (pathFn: () => void, _rect: any, draw: () => void) => {
      g.save();
      pathFn();
      try {
        draw();
      } finally {
        g.restore();
      }
    },
  };
  return { stage, drawCalls, boundsCalls, clipRects };
}

test("sampleSpeechMouth debounces 1-frame spikes and clamps closed near shot tail", async (t) => {
  const mod = await loadMicroActorModule();
  if (!mod) {
    t.skip("缺少 esbuild，跳过 microActor 打包单测");
    return;
  }
  const values = [
    0.02, 0.03, 0.04, 0.25, 0.04, // single-frame 0.25 at frame 3 after minHold window opens, then immediate drop at frame 4 must hold!
    0.35, 0.55, 0.62, 0.52, 0.28,
    0.05, 0.03, 0.02, 0.50, 0.60, // late syllable at 2.0+ sec vs tail clamp
  ];
  const env = { fps: 10, duration_s: 1.5, values };

  assert.equal(mod.sampleSpeechMouth(0.12, env), "closed");
  // Frame 3 switches to softOpen; frame 4 stays softOpen due to minHoldSec=0.18 (>=2 frames at 10fps)
  assert.equal(mod.sampleSpeechMouth(0.32, env, { minHoldSec: 0.18 }), "softOpen");
  assert.equal(mod.sampleSpeechMouth(0.42, env, { minHoldSec: 0.18 }), "softOpen");
  // Frame 7 reaches midOpen deterministically across reverse seek
  assert.equal(mod.sampleSpeechMouth(0.72, env, { minHoldSec: 0.15 }), "midOpen");
  // Repeat backwards seek gives identical result
  assert.equal(mod.sampleSpeechMouth(0.32, env, { minHoldSec: 0.18 }), "softOpen");
  // Tail near 15/16 forces closed
  assert.equal(mod.sampleSpeechMouth(1.42, env), "closed");
});

test("solveEyeState triggers deterministic blink on gaze transitions and stays open at pose11", async (t) => {
  const mod = await loadMicroActorModule();
  if (!mod) {
    t.skip("缺少 esbuild，跳过 microActor 打包单测");
    return;
  }
  const gaze = [
    { at: 0, eye: "glanceLeft" },
    { at: 1.95, eye: "open", triggerBlink: true },
  ];
  assert.equal(mod.solveEyeState(0.5, gaze, { span: 4.5 }).eye, "glanceLeft");
  // triggerBlink queues a blink slightly before the gaze turn (~1.89..2.02s)
  const midBlink = mod.solveEyeState(1.94, gaze, { span: 4.5 });
  assert.equal(midBlink.eye, "closed");
  assert.equal(midBlink.isBlinking, true);
  assert.equal(mod.solveEyeState(2.2, gaze, { span: 4.5 }).eye, "open");
  assert.equal(mod.solveEyeState(4.35, gaze, { span: 4.5 }).isBlinking, false);
});

test("drawMicroActor locks 100% base frame and aligns local eye/mouth patches exactly", async (t) => {
  const mod = await loadMicroActorModule();
  if (!mod) {
    t.skip("缺少 esbuild，跳过 microActor 打包单测");
    return;
  }
  const rig = {
    id: "presenter_rig",
    baseImageId: "rig_base",
    baseSize: [1024, 1024] as const,
    origin: [512, 980] as const,
    contentBounds: [180, 90, 840, 980] as const,
    eyes: {
      closed: { imageId: "rig_eyes_closed", x: 420, y: 260, w: 180, h: 70 },
      glanceLeft: { imageId: "rig_eyes_left", x: 420, y: 260, w: 180, h: 70 },
    },
    mouths: {
      softOpen: { imageId: "rig_mouth_soft", x: 460, y: 365, w: 100, h: 52 },
      midOpen: { imageId: "rig_mouth_mid", x: 460, y: 365, w: 100, h: 52 },
    },
  };
  const mock = makeMockStage({
    rig_base: { tag: "base" },
    rig_eyes_left: { tag: "eye_left" },
    rig_mouth_soft: { tag: "mouth_soft" },
  });
  const perf: any[] = [];
  const res = mod.drawMicroActor(mock.stage, 0.5, {
    rig,
    x: 990,
    y: 544,
    width: 460,
    spanOrBeat: 4.48,
    clipBottomY: 532,
    gazeBeats: [{ at: 0, eye: "glanceLeft" }],
    speech: { fps: 24, duration_s: 4.48, values: Array(108).fill(0.26) },
    context: { performanceStates: perf },
  });
  assert.equal(res.eye, "glanceLeft");
  assert.equal(res.mouth, "softOpen");
  assert.equal(mock.drawCalls.length, 3);
  assert.equal(mock.drawCalls[0].im.tag, "base");
  assert.equal(mock.drawCalls[1].im.tag, "eye_left");
  // Eye patch drawn in local base pixel space relative to origin [512, 980]
  assert.deepEqual(mock.drawCalls[1].args, [420 - 512, 260 - 980, 180, 70]);
  assert.equal(mock.drawCalls[2].im.tag, "mouth_soft");
  assert.deepEqual(mock.drawCalls[2].args, [460 - 512, 365 - 980, 100, 52]);
  assert.equal(perf[0].pose, "glanceLeft:softOpen");
});
