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

async function loadActorModule() {
  const esbuild = dependency("esbuild");
  if (!esbuild) return null;
  const bundle = await esbuild.build({
    entryPoints: [path.join(root, "src/kit/actor.ts")],
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

async function loadRoomsModule() {
  const esbuild = dependency("esbuild");
  if (!esbuild) return null;
  const bundle = await esbuild.build({
    entryPoints: [path.join(root, "src/kit/rooms.ts")],
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

function makeMockStage(assets: Record<string, any> = {}, images: Record<string, any> = {}) {
  const drawCalls: any[] = [];
  const boundsCalls: any[] = [];
  const clipRects: any[] = [];
  const transforms: Array<{ tx: number; ty: number; sx: number; sy: number; rot: number }> = [];
  let state = { tx: 0, ty: 0, sx: 1, sy: 1, rot: 0, alpha: 1 };
  const stack: any[] = [];
  const g: any = {
    fillStyle: "",
    globalAlpha: 1,
    shadowColor: "",
    shadowBlur: 0,
    shadowOffsetX: 0,
    shadowOffsetY: 0,
    save: () => {
      stack.push({ ...state, alpha: g.globalAlpha });
    },
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
      drawCalls.push({ im, args, transform: { ...state }, alpha: g.globalAlpha });
    },
  };
  const stage: any = {
    width: 1280,
    height: 720,
    tracking: true,
    g,
    assets,
    images,
    shadow: () => {},
    bounds: (rect: any) => {
      if (stage.tracking) boundsCalls.push({ ...rect, transform: { ...state } });
    },
    group: (pose: any, draw: () => void) => {
      g.save();
      g.translate(pose.x, pose.y);
      g.rotate(pose.rotation || 0);
      g.scale(pose.scale ?? 1, pose.scale ?? 1);
      g.globalAlpha *= pose.opacity ?? 1;
      try {
        draw();
      } finally {
        g.restore();
      }
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
  return { stage, drawCalls, boundsCalls, clipRects, transforms };
}

test("actorCadence is deterministic under reverse seeks, aligns to cues, and zeroes at pose11", async (t) => {
  const actor = await loadActorModule();
  if (!actor) {
    t.skip("缺少 esbuild，跳过 actor 打包单测");
    return;
  }
  const beat = { id: "S01", title: "t", start: 10.0, end: 18.0, events: {} };
  const cues = [
    { start: 10.2, end: 13.5 },
    { start: 13.8, end: 17.6 },
  ];
  const sampleA = actor.actorCadence(3.25, beat, { cues, seed: 42 });
  actor.actorCadence(7.9, beat, { cues, seed: 42 });
  actor.actorCadence(0.1, beat, { cues, seed: 42 });
  const sampleB = actor.actorCadence(3.25, beat, { cues, seed: 42 });
  assert.deepEqual(sampleA, sampleB);
  assert.ok(sampleA.env > 0.5 && (Math.abs(sampleA.dy) > 0 || Math.abs(sampleA.rotation) > 0));

  // Pose11 (15/16 of 8.0s = 7.5s) must be exact zero with blink suppressed.
  const pose11 = actor.actorCadence((8.0 * 15) / 16, beat, { cues, seed: 42 });
  assert.deepEqual(pose11, {
    dx: 0,
    dy: 0,
    rotation: 0,
    nod: 0,
    lean: 0,
    blink01: 0,
    env: 0,
  });
});

test("actorTransition yields pre-switch anticipation, post-switch spring settle, and clean convergence", async (t) => {
  const actor = await loadActorModule();
  if (!actor) {
    t.skip("缺少 esbuild，跳过 actor 打包单测");
    return;
  }
  const beats = [
    { at: 0, pose: "greet_front", lean: 0 },
    { at: 2.0, pose: "remind_serious_front", lean: 0.02 },
  ];
  const beforeSwitch = actor.actorTransition(1.94, beats, { span: 8.0 });
  assert.equal(beforeSwitch.pose, "greet_front");
  assert.equal(beforeSwitch.inTransition, true);
  assert.equal(beforeSwitch.scaleX, 1);
  assert.equal(beforeSwitch.scaleY, 1);
  assert.ok(beforeSwitch.dy > 0, "pre-switch weight settle dips gently without cartoon squash/stretch");

  const afterSwitch = actor.actorTransition(2.05, beats, { span: 8.0, blendWindow: 0.08 });
  assert.equal(afterSwitch.pose, "remind_serious_front");
  assert.ok(afterSwitch.blend > 0 && afterSwitch.blend < 1);
  assert.ok(afterSwitch.inTransition);

  const settled = actor.actorTransition(4.5, beats, { span: 8.0 });
  assert.equal(settled.blend, 1);
  assert.equal(settled.inTransition, false);
  assert.ok(Math.abs(settled.scaleX - 1) < 1e-6 && Math.abs(settled.scaleY - 1) < 1e-6);
});

test("drawActorAtlas clips non-uniform rects cleanly, maintains origin alignment, and suppresses blink on excluded poses", async (t) => {
  const actor = await loadActorModule();
  if (!actor) {
    t.skip("缺少 esbuild，跳过 actor 打包单测");
    return;
  }
  const spec = {
    imageId: "presenter_acting_v2",
    blinkCell: "listen_blink_soft",
    defaultCell: "greet_front",
    cells: {
      greet_front: { name: "greet_front", rect: [0, 0, 385, 350], origin: [192, 340], contentBounds: [30, 18, 336, 343] },
      listen_blink_soft: { name: "listen_blink_soft", rect: [1146, 0, 390, 350], origin: [195, 340], contentBounds: [40, 18, 346, 343] },
      remind_serious_front: { name: "remind_serious_front", rect: [0, 685, 385, 339], origin: [192, 330], contentBounds: [20, 12, 356, 332] },
    },
  };

  // Find a deterministic blink time by scanning within [0.4, 5.5]
  let blinkT = -1;
  for (let tt = 0.4; tt < 5.5; tt += 0.02) {
    if (actor.actorCadence(tt, 8.0, { seed: 31 }).blink01 > 0.6) {
      blinkT = tt;
      break;
    }
  }
  assert.ok(blinkT > 0.4, "must emit a deterministic blink pulse within a normal 8s shot");

  const mock = makeMockStage({}, { presenter_acting_v2: { width: 1536, height: 1024 } });
  const perf: any[] = [];
  const resNoBlink = actor.drawActorAtlas(mock.stage, blinkT, {
    spec,
    beats: [{ at: 0, pose: "greet_front" }],
    x: 920,
    y: 520,
    width: 340,
    spanOrBeat: 8.0,
    seed: 31,
    clipBottomY: 515,
  });
  assert.equal(resNoBlink.cellName, "greet_front", "default allowBlink=false must not swap cells");

  const resBlink = actor.drawActorAtlas(mock.stage, blinkT, {
    spec,
    beats: [{ at: 0, pose: "greet_front" }],
    x: 920,
    y: 520,
    width: 340,
    spanOrBeat: 8.0,
    seed: 31,
    clipBottomY: 515,
    allowBlink: true,
    blinkCompatibleCells: ["greet_front"],
    context: { performanceStates: perf },
  });
  assert.equal(resBlink.cellName, "listen_blink_soft");
  assert.equal(mock.drawCalls[1].args[0], 1146);
  assert.equal(mock.clipRects[0].h, 715);
  assert.equal(perf[0].asset_id, "presenter_acting_v2");

  // Tail at 15/16 must settle cleanly and never blink.
  const mockTail = makeMockStage({}, { presenter_acting_v2: { width: 1536, height: 1024 } });
  const resTail = actor.drawActorAtlas(mockTail.stage, 7.5, {
    spec,
    beats: [{ at: 0, pose: "greet_front" }, { at: 3.0, pose: "remind_serious_front" }],
    x: 920,
    y: 520,
    width: 340,
    spanOrBeat: 8.0,
    seed: 31,
  });
  assert.equal(resTail.cellName, "remind_serious_front");
  assert.equal(mockTail.drawCalls[0].args[1], 685);
});

test("drawActorPose & drawActorWalk preserve calibration, facing flip, and foot-locked stride", async (t) => {
  const actor = await loadActorModule();
  if (!actor) {
    t.skip("缺少 esbuild，跳过 actor 打包单测");
    return;
  }
  const cal = {
    status: "calibrated",
    source_sha256: "abc",
    source_size: { width: 1024, height: 1536 },
    from: { x: 0.5, y: 0.05 },
    to: { x: 0.5, y: 0.95 },
    span_cm: 165,
    basis: "test",
  };
  const assets = {
    stand: {
      asset_id: "stand",
      registration: { anchors: { feet: { x: 0.5, y: 0.96 } } },
      visible_bounds: { x: 0.25, y: 0.05, w: 0.5, h: 0.91 },
      human_scale: { nominal_height_cm: 165, calibration: cal },
    },
    point: {
      asset_id: "point",
      registration: { anchors: { feet: { x: 0.5, y: 0.96 } } },
      visible_bounds: { x: 0.25, y: 0.05, w: 0.6, h: 0.91 },
      human_scale: { nominal_height_cm: 165, calibration: cal },
    },
  };
  const images = {
    stand: { width: 1024, height: 1536 },
    point: { width: 1024, height: 1536 },
    walk_sheet: { width: 1536, height: 1024 },
  };
  // Actor on right side of stage (x=960) without explicit facing should face left (flipped if sourceFacesRight=true)
  const mockRight = makeMockStage(assets, images);
  actor.drawActorPose(mockRight.stage, 2.02, {
    x: 960,
    ground: 552,
    pixelsPerCm: 2.2,
    beats: [{ at: 0, pose: "stand" }, { at: 2.0, pose: "point" }],
    spanOrBeat: 6.0,
    blendWindow: 0.08,
  });
  assert.equal(mockRight.drawCalls.length, 2, "crossfade renders prev and current pose during 0.08s blend");
  assert.ok(mockRight.drawCalls[1].transform.sx < 0, "character on right side flips to face left stage center");
  assert.equal(mockRight.boundsCalls.length, 1, "only active target pose registers layout bounds");

  // Foot-locked walk steps deterministically
  const walkFrames = Array.from({ length: 8 }, (_, idx) => ({
    name: `walk-${idx}`,
    rect: [idx * 100, 0, 100, 200] as const,
    origin: [50, 190] as const,
  }));
  const mockWalkStart = makeMockStage(assets, images);
  const w0 = actor.drawActorWalk(mockWalkStart.stage, 0.2, {
    imageId: "walk_sheet",
    frames: walkFrames,
    start: 0.2,
    end: 3.8,
    fromX: 200,
    toX: 520,
    ground: 552,
    pixelsPerCm: 2.2,
    sourcePixelsPerCm: 3.0,
  });
  assert.equal(w0.frameIndex, 0);
  assert.equal(w0.x, 200);

  const mockWalkEnd = makeMockStage(assets, images);
  const wEnd = actor.drawActorWalk(mockWalkEnd.stage, 4.0, {
    imageId: "walk_sheet",
    frames: walkFrames,
    start: 0.2,
    end: 3.8,
    fromX: 200,
    toX: 520,
    ground: 552,
    pixelsPerCm: 2.2,
    sourcePixelsPerCm: 3.0,
  });
  assert.equal(wEnd.frameIndex, 7);
  assert.equal(wEnd.x, 520);
});

test("drawActorEdgeHand hides severed cuff off-canvas and settles cleanly at pose11", async (t) => {
  const actor = await loadActorModule();
  if (!actor) {
    t.skip("缺少 esbuild，跳过 actor 打包单测");
    return;
  }
  const assets = {
    arm: {
      asset_id: "arm",
      visible_bounds: { x: 0.04, y: 0.2, w: 0.92, h: 0.6 },
    },
  };
  const images = {
    arm: { width: 2172, height: 724 },
  };
  const mockPre = makeMockStage(assets, images);
  const pre = actor.drawActorEdgeHand(mockPre.stage, 0.2, {
    imageId: "arm",
    reachX: 460,
    y: 420,
    start: 0.8,
    edge: "left",
    spanOrBeat: 8.0,
  });
  assert.equal(pre.extension, 0);
  assert.equal(mockPre.drawCalls.length, 0);

  const mockTail = makeMockStage(assets, images);
  const perf: any[] = [];
  const res = actor.drawActorEdgeHand(mockTail.stage, 7.5, {
    imageId: "arm",
    reachX: 460,
    y: 420,
    start: 0.8,
    edge: "left",
    spanOrBeat: 8.0,
    context: { performanceStates: perf },
  });
  assert.ok(res.cuffX < 0, "severed shoulder/cuff edge must stay outside left canvas edge");
  assert.ok(Math.abs(res.tipX - 460) < 0.2, "hand tip must settle accurately on reachX at pose11");
  assert.equal(perf[0].pose, "edge_hand_left");
});

test("atlasFromSequence adapts imported sequence.json number[] arrays into typed ActorAtlasSpec", async (t) => {
  const actor = await loadActorModule();
  if (!actor) {
    t.skip("缺少 esbuild，跳过 actor 打包单测");
    return;
  }
  const fakeSeq = {
    schema: "mac_motion_study/v1",
    actor_atlas: {
      defaultCell: "listen_neutral",
      blinkCell: "look_down_paper",
      cells: {
        listen_neutral: {
          name: "listen_neutral",
          rect: [0, 0, 385, 350],
          origin: [187.5, 343],
          contentBounds: [30, 18, 336, 343],
        },
        look_down_paper: {
          name: "look_down_paper",
          rect: [772, 0, 374, 350],
          origin: [193.5, 343],
          contentBounds: [33, 17, 335, 343],
        },
      },
    },
  };
  const spec = actor.atlasFromSequence(fakeSeq, "presenter_acting__sheet");
  assert.equal(spec.imageId, "presenter_acting__sheet");
  assert.equal(spec.defaultCell, "listen_neutral");
  assert.equal(spec.blinkCell, "look_down_paper");
  assert.deepEqual(spec.cells.listen_neutral.rect, [0, 0, 385, 350]);
  assert.deepEqual(spec.cells.look_down_paper.origin, [193.5, 343]);

  const mock = makeMockStage({}, { presenter_acting__sheet: { width: 1536, height: 1024 } });
  const drawn = actor.drawActorAtlas(mock.stage, 0.2, {
    spec,
    beats: [{ at: 0, pose: "listen_neutral" }],
    x: 920,
    y: 520,
    width: 340,
    spanOrBeat: 8.0,
    clipBottomY: 515,
  });
  assert.equal(drawn.cellName, "listen_neutral");
  assert.equal(mock.drawCalls[0].args[0], 0);
});

test("drawForegroundDesk aligns visible_bounds top edge to topY, returns clipBottomY, and stays out of bounds tracking by default", async (t) => {
  const actor = await loadActorModule();
  if (!actor) {
    t.skip("缺少 esbuild，跳过 actor 打包单测");
    return;
  }
  const mock = makeMockStage(
    {
      bg_foreground_desk: {
        visible_bounds: { x: 0, y: 0.5, w: 1, h: 0.5 },
      },
    },
    { bg_foreground_desk: { width: 1536, height: 1024 } },
  );
  const res = actor.drawForegroundDesk(mock.stage, { topY: 508, overscanX: 48, bottomOverscan: 16 });
  assert.equal(res.topY, 508);
  assert.equal(res.clipBottomY, 516);
  assert.equal(res.wallSafeBottomY, 494);
  assert.equal(res.surfaceSafeBottomY, 537);
  assert.equal(res.frontLipTopY, 547);
  assert.equal(res.frontPanelTopY, 562);
  assert.ok(res.wallSafeBottomY < res.topY && res.topY < res.surfaceSafeBottomY && res.surfaceSafeBottomY < res.frontLipTopY && res.frontLipTopY < res.frontPanelTopY);
  assert.equal(mock.drawCalls.length, 1);
  // drawImage(im, sx, sy, sw, sh, dx, dy, dw, dh)
  assert.deepEqual(mock.drawCalls[0].args, [0, 512, 1536, 512, -48, 508, 1376, 228]);
  assert.equal(mock.boundsCalls.length, 0, "foreground backdrop must not pollute subject bounds by default");
  assert.equal(mock.stage.tracking, true, "stage.tracking must be restored after drawForegroundDesk");

  const highDesk = actor.drawForegroundDesk(mock.stage, { topY: 414, overscanX: 48, bottomOverscan: 16 });
  assert.equal(highDesk.surfaceSafeBottomY, 454);
  assert.equal(highDesk.frontLipTopY, 469);
  assert.equal(highDesk.frontPanelTopY, 490);
  assert.equal(highDesk.wallSafeBottomY, 400);
});

test("drawCloseWallBackdrop crops upper wall above floor line and restores tracking", async (t) => {
  const rooms = await loadRoomsModule();
  if (!rooms) {
    t.skip("缺少 esbuild，跳过 rooms 打包单测");
    return;
  }
  const mock = makeMockStage({}, { bg_home: { width: 1408, height: 768 } });
  rooms.drawCloseWallBackdrop(mock.stage, "bg_home");
  assert.equal(mock.drawCalls.length, 1);
  const args = mock.drawCalls[0].args;
  assert.equal(args[0], 0);
  assert.equal(args[1], 0);
  assert.equal(args[2], 1408);
  assert.ok(Math.abs(args[3] - 768 * 0.84) < 0.01);
  assert.deepEqual(args.slice(4), [-80, -40, 1440, 780]);
  assert.equal(mock.stage.tracking, true, "stage.tracking must remain intact");
});
