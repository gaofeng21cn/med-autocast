import type { Stage } from "./stage";
import type { Beat, Point, ShotContext } from "./types";
import { humanImageWidth } from "./humanScale";
import { SPRING, clamp, hash, mix, phase, progress, shotBreath, springEase, type SpringPreset } from "./motion";
import { contactShadow } from "./staging";

export type ActorBeat = {
  at: number;
  pose: string;
  facing?: "left" | "right";
  sourceFacesRight?: boolean;
  lean?: number;
  nod?: number;
  event?: string;
};

export type AtlasCell = {
  name: string;
  rect: readonly [number, number, number, number];
  origin: readonly [number, number];
  contentBounds?: readonly [number, number, number, number];
};

export type ActorAtlasSpec = {
  imageId: string;
  cells: Record<string, AtlasCell>;
  blinkCell?: string;
  defaultCell?: string;
};

export type ActorCadenceState = {
  dx: number;
  dy: number;
  rotation: number;
  nod: number;
  lean: number;
  blink01: number;
  env: number;
};

export type ActorTransitionState = {
  pose: string;
  prevPose: string;
  activeBeat: ActorBeat;
  blend: number;
  inTransition: boolean;
  scaleX: number;
  scaleY: number;
  dy: number;
  rotation: number;
  lean: number;
  nod: number;
  facing?: "left" | "right";
  envelope: number;
};

export type CueSpan = { start: number; end: number };

export function resolveShotCues(
  cues: readonly CueSpan[] | undefined,
  beat: Pick<Beat, "start" | "end"> | number,
): CueSpan[] {
  if (!cues?.length) return [];
  if (typeof beat === "number") {
    return cues
      .filter((c) => c.end > 0 && c.start < beat)
      .map((c) => ({ start: Math.max(0, c.start), end: Math.min(beat, c.end) }));
  }
  const span = Math.max(0.5, beat.end - beat.start);
  const local: CueSpan[] = [];
  for (const c of cues) {
    if (c.end > beat.start + 0.04 && c.start < beat.end - 0.04) {
      local.push({
        start: Math.max(0, c.start - beat.start),
        end: Math.min(span, c.end - beat.start),
      });
    }
  }
  return local;
}

function tailEnvelope(t: number, span: number, tailMargin?: number, fadeWindow = 0.65): number {
  const margin = Math.max(tailMargin ?? 1.65, span * 0.17);
  const settleBefore = Math.max(0, span - margin);
  if (t >= settleBefore) return 0;
  const fw = Math.max(0.05, fadeWindow);
  const fadeStart = settleBefore - fw;
  if (t > fadeStart) {
    return 1 - phase(t, fadeStart, settleBefore);
  }
  return 1;
}

/**
 * Deterministic phrase-synced micro-cadence for seated/standing medical explainers.
 * Produces gentle breathing, cue-aligned nods/leans, and periodic soft blinks while
 * clamping cleanly to exact zero before the 15/16 shot-tail frame (`pose11`).
 */
export function actorCadence(
  t: number,
  spanOrBeat: number | Pick<Beat, "start" | "end">,
  opts: {
    cues?: readonly CueSpan[];
    seed?: number;
    blinkInterval?: number;
    blinkDuration?: number;
    tailMargin?: number;
    fadeWindow?: number;
    ampY?: number;
    ampRot?: number;
    ampNod?: number;
  } = {},
): ActorCadenceState {
  const span =
    typeof spanOrBeat === "number"
      ? Math.max(0.5, spanOrBeat)
      : Math.max(0.5, spanOrBeat.end - spanOrBeat.start);
  const seed = opts.seed ?? 17;
  const env = tailEnvelope(t, span, opts.tailMargin, opts.fadeWindow ?? 0.65);
  if (env <= 0) {
    return { dx: 0, dy: 0, rotation: 0, nod: 0, lean: 0, blink01: 0, env: 0 };
  }

  const breath = shotBreath(t, spanOrBeat, seed, {
    ampY: opts.ampY ?? 0.9,
    ampRot: opts.ampRot ?? 0.0028,
    hz: 0.36,
    tailMargin: opts.tailMargin,
    fadeWindow: opts.fadeWindow,
  });

  const localCues = resolveShotCues(opts.cues, spanOrBeat);
  let nod = 0;
  let lean = 0;
  const ampNod = opts.ampNod ?? 1.4;

  for (let i = 0; i < localCues.length; i++) {
    const q = localCues[i];
    const qLen = q.end - q.start;
    if (qLen < 0.35) continue;
    // Slight attentive lift at phrase onset, soft settling nod near phrase completion.
    const onsetDt = t - q.start;
    if (onsetDt >= 0 && onsetDt <= 0.42) {
      lean += Math.sin(Math.PI * clamp(onsetDt / 0.42)) * 0.012;
    }
    const nodAt = Math.max(q.start + 0.25, q.end - 0.34);
    const nodDt = t - nodAt;
    if (nodDt >= 0 && nodDt <= 0.36 && (i % 2 === 0 || qLen >= 2.1)) {
      nod += Math.sin(Math.PI * clamp(nodDt / 0.36)) * ampNod;
    }
  }

  const interval = Math.max(1.8, opts.blinkInterval ?? 3.6);
  const blinkDur = clamp(opts.blinkDuration ?? 0.13, 0.08, 0.24);
  const margin = Math.max(opts.tailMargin ?? 1.65, span * 0.17);
  const settleBefore = Math.max(0, span - margin);
  let blink01 = 0;
  if (t > 0.28 && t < settleBefore - 0.18 && env > 0.45) {
    const cycle = Math.floor(t / interval);
    const jitter = 0.55 + hash(seed * 31 + cycle * 19) * Math.max(0.4, interval - 1.2);
    const blinkStart = cycle * interval + Math.min(interval - blinkDur - 0.12, jitter);
    const u = (t - blinkStart) / blinkDur;
    if (u >= 0 && u <= 1) {
      blink01 = Math.sin(Math.PI * u);
    }
  }

  return {
    dx: breath.dx * env,
    dy: (breath.dy + nod * 0.45) * env,
    rotation: (breath.rotation + lean * 0.65) * env,
    nod: nod * env,
    lean: lean * env,
    blink01,
    env,
  };
}

/**
 * Deterministic pose-transition solver combining anticipation compression and damped spring settle.
 */
export function actorTransition(
  t: number,
  beats: readonly ActorBeat[],
  opts: {
    blendWindow?: number;
    anticipationWindow?: number;
    settleWindow?: number;
    preset?: SpringPreset;
    span?: number;
    tailMargin?: number;
  } = {},
): ActorTransitionState {
  if (!beats.length) {
    throw Error("actorTransition 需要至少一个 ActorBeat");
  }
  const sorted = [...beats].sort((a, b) => a.at - b.at);
  let activeIdx = 0;
  for (let i = 0; i < sorted.length; i++) {
    if (t >= sorted[i].at) activeIdx = i;
    else break;
  }
  const active = sorted[activeIdx];
  const prev = sorted[Math.max(0, activeIdx - 1)];
  const next = activeIdx + 1 < sorted.length ? sorted[activeIdx + 1] : null;

  const antWin = Math.max(0.04, opts.anticipationWindow ?? 0.1);
  const settleWin = Math.max(0.16, opts.settleWindow ?? 0.32);
  const blendWin = Math.max(0, opts.blendWindow ?? 0);
  const preset = opts.preset ?? SPRING.smooth;

  const env = opts.span !== undefined ? tailEnvelope(t, opts.span, opts.tailMargin, 0.55) : 1;

  const scaleX = 1;
  const scaleY = 1;
  let dy = 0;
  let rotation = 0;
  let inTransition = false;
  let blend = 1;

  // 1. Pre-switch subtle weight settle (zero cartoon squash/stretch).
  if (next && next.pose !== active.pose) {
    const timeToNext = next.at - t;
    if (timeToNext > 0 && timeToNext <= antWin) {
      const u = Math.sin(Math.PI * 0.5 * clamp(1 - timeToNext / antWin));
      dy += 0.9 * u * env;
      rotation -= 0.004 * u * env;
      inTransition = true;
    }
  }

  // 2. Post-switch smooth non-bouncy weight recovery and explicit-only crossfade.
  if (activeIdx > 0 && prev.pose !== active.pose) {
    const dt = t - active.at;
    if (dt >= 0 && dt < Math.max(settleWin, blendWin)) {
      inTransition = true;
    }
    if (blendWin > 0 && dt >= 0 && dt < blendWin) {
      blend = clamp(dt / blendWin);
    }
    if (dt >= 0 && dt < settleWin) {
      const sp = springEase(dt, preset.stiffness, preset.damping);
      dy += 0.9 * (1 - sp) * env;
      rotation += 0.005 * (1 - sp) * env;
    }
  }

  const settleMorph = activeIdx > 0 ? clamp(springEase(Math.max(0, t - active.at), SPRING.smooth.stiffness, SPRING.smooth.damping)) : 1;
  const lean = mix(prev.lean ?? 0, active.lean ?? 0, settleMorph);
  const nod = mix(prev.nod ?? 0, active.nod ?? 0, settleMorph);

  return {
    pose: active.pose,
    prevPose: prev.pose,
    activeBeat: active,
    blend,
    inTransition,
    scaleX,
    scaleY,
    dy,
    rotation: rotation + lean * env,
    lean,
    nod,
    facing: active.facing,
    envelope: env,
  };
}

function recordActorState(
  context: Partial<ShotContext> | undefined,
  actorId: string,
  assetId: string,
  pose: string,
  eventName: string,
  t: number,
  transition: number,
) {
  const perf = (context as { performanceStates?: unknown[] } | undefined)?.performanceStates;
  if (Array.isArray(perf)) {
    perf.push({
      actor_id: actorId,
      asset_id: assetId,
      pose,
      event: eventName,
      elapsed: t,
      transition,
    });
  }
}

/**
 * Draw a full-body calibrated character pose sequence with feet-anchored anticipation/spring,
 * phrase-synced micro-cadence, grounded contact shadow, and world-coordinate facing safety.
 */
export function drawActorPose(
  stage: Stage,
  t: number,
  opts: {
    x: number;
    ground: number;
    pixelsPerCm: number;
    beats: readonly ActorBeat[];
    spanOrBeat: number | Pick<Beat, "start" | "end">;
    cues?: readonly CueSpan[];
    seed?: number;
    facing?: "left" | "right";
    sourceFacesRight?: boolean;
    blendWindow?: number;
    shadowW?: number;
    opacity?: number;
    lift?: number;
    actorId?: string;
    context?: Partial<ShotContext>;
    enterFrom?: { x: number; start: number; duration?: number; preset?: SpringPreset };
  },
): { assetId: string; pose: string; x: number; foot: number } {
  const span =
    typeof opts.spanOrBeat === "number"
      ? Math.max(0.5, opts.spanOrBeat)
      : Math.max(0.5, opts.spanOrBeat.end - opts.spanOrBeat.start);
  const trans = actorTransition(t, opts.beats, {
    blendWindow: opts.blendWindow ?? 0,
    span,
  });
  const cad = actorCadence(t, opts.spanOrBeat, {
    cues: opts.cues,
    seed: opts.seed ?? 23,
  });

  let drawX = opts.x;
  let enterProgress = 1;
  if (opts.enterFrom) {
    const dur = Math.max(0.15, opts.enterFrom.duration ?? 0.55);
    const dt = t - opts.enterFrom.start;
    if (dt <= 0) {
      drawX = opts.enterFrom.x;
      enterProgress = 0;
    } else {
      const ease = springEase(dt, (opts.enterFrom.preset ?? SPRING.paper).stiffness, (opts.enterFrom.preset ?? SPRING.paper).damping);
      drawX = mix(opts.enterFrom.x, opts.x, clamp(ease, 0, 1.05));
      enterProgress = clamp(dt / dur);
    }
  }

  const baseOpacity = (opts.opacity ?? 1) * (opts.enterFrom ? clamp(enterProgress * 3) : 1);
  if (baseOpacity <= 0.02) {
    return { assetId: trans.pose, pose: trans.pose, x: drawX, foot: opts.ground };
  }

  const facing = trans.facing ?? opts.facing ?? (opts.x < stage.width * 0.5 ? "right" : "left");

  const resolveSourceFacesRight = (assetId: string): boolean => {
    if (assetId === trans.activeBeat.pose && trans.activeBeat.sourceFacesRight !== undefined) {
      return trans.activeBeat.sourceFacesRight;
    }
    const matching = opts.beats.filter((b) => b.pose === assetId && b.sourceFacesRight !== undefined);
    const prior = matching.filter((b) => b.at <= t).pop() ?? matching[0];
    if (prior?.sourceFacesRight !== undefined) {
      return prior.sourceFacesRight;
    }
    const meta = stage.assets[assetId] as { registration?: { facing?: string } } | undefined;
    if (meta?.registration?.facing === "right") return true;
    if (meta?.registration?.facing === "left") return false;
    return opts.sourceFacesRight ?? true;
  };

  const drawSingle = (assetId: string, alpha: number, recordBounds: boolean) => {
    const im = stage.images[assetId];
    const asset = stage.assets[assetId] as {
      registration?: { facing?: string; anchors?: Record<string, Point> };
      visible_bounds?: { x: number; y: number; w: number; h: number };
    } | undefined;
    if (!im || !asset) throw Error(`缺少角色标定姿态 ${assetId}`);
    const flip = resolveSourceFacesRight(assetId) !== (facing === "right");
    const w = humanImageWidth(stage.assets[assetId], im.width, im.height, opts.pixelsPerCm);
    const k = w / im.width;
    const h = im.height * k;
    const m = asset.visible_bounds ?? { x: 0, y: 0, w: 1, h: 1 };
    const feet = asset.registration?.anchors?.feet ?? { x: m.x + m.w * 0.5, y: m.y + m.h };
    const prevTracking = stage.tracking;
    if (!recordBounds) stage.tracking = false;
    try {
      const g = stage.g;
      g.save();
      g.translate(drawX + cad.dx, opts.ground + cad.dy + trans.dy);
      g.rotate(cad.rotation + trans.rotation);
      g.scale((flip ? -1 : 1) * trans.scaleX, trans.scaleY);
      g.globalAlpha *= alpha;
      stage.shadow(opts.lift ?? 2);
      g.drawImage(im, -feet.x * w, -feet.y * h, w, h);
      stage.bounds({
        x: (m.x - feet.x) * w,
        y: (m.y - feet.y) * h,
        w: m.w * w,
        h: m.h * h,
        name: assetId,
      });
      g.restore();
    } finally {
      stage.tracking = prevTracking;
    }
  };

  contactShadow(stage, drawX, opts.ground + 3, opts.shadowW ?? 58, 12, 0.35, baseOpacity);
  if (trans.blend < 0.995 && trans.prevPose !== trans.pose && stage.images[trans.prevPose]) {
    drawSingle(trans.prevPose, baseOpacity * (1 - trans.blend * 0.55), false);
    drawSingle(trans.pose, baseOpacity * trans.blend, true);
  } else {
    drawSingle(trans.pose, baseOpacity, true);
  }

  recordActorState(
    opts.context,
    opts.actorId ?? "presenter",
    trans.pose,
    trans.activeBeat.pose,
    trans.activeBeat.event ?? "actor_pose",
    t,
    trans.inTransition ? trans.blend : 1,
  );

  return { assetId: trans.pose, pose: trans.pose, x: drawX, foot: opts.ground };
}

/**
 * Draw a cell from a non-uniform character acting atlas anchored on its head/shoulder `origin`,
 * driving phrase-synced gestures, smooth state anticipation/bounce, and automatic subtle blinks.
 */
export function drawActorAtlas(
  stage: Stage,
  t: number,
  opts: {
    spec: ActorAtlasSpec;
    beats: readonly ActorBeat[];
    x: number;
    y: number;
    width?: number;
    spanOrBeat: number | Pick<Beat, "start" | "end">;
    cues?: readonly CueSpan[];
    seed?: number;
    facing?: "left" | "right";
    sourceFacesRight?: boolean;
    clipBottomY?: number;
    allowBlink?: boolean;
    blinkCompatibleCells?: readonly string[];
    blinkExclude?: readonly string[];
    opacity?: number;
    lift?: number;
    shadowW?: number;
    actorId?: string;
    context?: Partial<ShotContext>;
  },
): { cellName: string; x: number; y: number } {
  const span =
    typeof opts.spanOrBeat === "number"
      ? Math.max(0.5, opts.spanOrBeat)
      : Math.max(0.5, opts.spanOrBeat.end - opts.spanOrBeat.start);
  const trans = actorTransition(t, opts.beats, {
    blendWindow: 0,
    span,
  });
  const cad = actorCadence(t, opts.spanOrBeat, {
    cues: opts.cues,
    seed: opts.seed ?? 31,
  });

  const canBlink =
    Boolean(opts.allowBlink) &&
    Boolean(opts.spec.blinkCell && opts.spec.cells[opts.spec.blinkCell]) &&
    !trans.inTransition &&
    cad.blink01 > 0.5 &&
    (opts.blinkCompatibleCells ? opts.blinkCompatibleCells.includes(trans.pose) : false) &&
    !(opts.blinkExclude ?? ["look_down_read", "listen_blink_soft", "think_chin"]).includes(trans.pose);

  const cellName = canBlink && opts.spec.blinkCell ? opts.spec.blinkCell : trans.pose;
  const cell =
    opts.spec.cells[cellName] ??
    (opts.spec.defaultCell ? opts.spec.cells[opts.spec.defaultCell] : undefined) ??
    Object.values(opts.spec.cells)[0];
  if (!cell) throw Error(`表演图集缺少姿态格 ${cellName}`);

  const im = stage.images[opts.spec.imageId];
  if (!im) throw Error(`缺少表演图集资源 ${opts.spec.imageId}`);

  const [sx, sy, sw, sh] = cell.rect;
  const [ox, oy] = cell.origin;
  const targetW = opts.width ?? 360;
  const scale = targetW / Math.max(1, sw);
  const facing = trans.facing ?? opts.facing;
  const sourceFacesRight = opts.sourceFacesRight ?? true;
  const flip = facing !== undefined ? sourceFacesRight !== (facing === "right") : false;
  const opacity = opts.opacity ?? 1;

  if (opacity <= 0.02) {
    return { cellName, x: opts.x, y: opts.y };
  }

  const drawBody = () => {
    const g = stage.g;
    const drawX = opts.x + cad.dx;
    const drawY = opts.y + cad.dy + trans.dy;
    const [bx0, by0, bx1, by1] = cell.contentBounds ?? [0, 0, sw, sh];
    if ((opts.shadowW ?? 0) > 0 && opts.clipBottomY !== undefined) {
      contactShadow(stage, drawX, opts.clipBottomY + 2, opts.shadowW ?? 90, 14, 0.28, opacity);
    }
    g.save();
    g.translate(drawX, drawY);
    g.rotate(cad.rotation + trans.rotation);
    g.scale((flip ? -scale : scale) * trans.scaleX, scale * trans.scaleY);
    g.globalAlpha *= opacity;
    stage.shadow(opts.lift ?? 2);
    g.drawImage(im, sx, sy, sw, sh, -ox, -oy, sw, sh);
    stage.bounds({
      x: bx0 - ox,
      y: by0 - oy,
      w: Math.max(1, bx1 - bx0),
      h: Math.max(1, by1 - by0),
      name: `${opts.spec.imageId}:${cell.name}`,
    });
    g.restore();
  };

  if (opts.clipBottomY !== undefined) {
    const topClip = -200;
    const clipH = Math.max(40, opts.clipBottomY - topClip);
    const clipRect = { x: 0, y: topClip, w: stage.width, h: clipH };
    stage.clip(
      () => {
        stage.g.beginPath();
        stage.g.rect(clipRect.x, clipRect.y, clipRect.w, clipRect.h);
      },
      clipRect,
      drawBody,
    );
  } else {
    drawBody();
  }

  recordActorState(
    opts.context,
    opts.actorId ?? "presenter",
    opts.spec.imageId,
    cell.name,
    trans.activeBeat.event ?? "actor_atlas_beat",
    t,
    trans.inTransition ? 0.5 : 1,
  );

  return { cellName, x: opts.x, y: opts.y };
}

/**
 * Draw a foot-locked character walk cycle where world x advances in discrete contact strides,
 * eliminating cut-paper floor sliding while staying 100% deterministic under random seeks.
 */
export function drawActorWalk(
  stage: Stage,
  t: number,
  opts: {
    imageId: string;
    frames: readonly AtlasCell[];
    start: number;
    end: number;
    fromX: number;
    toX: number;
    ground: number;
    pixelsPerCm: number;
    sourcePixelsPerCm: number;
    period?: number;
    sourceFacesRight?: boolean;
    opacity?: number;
    lift?: number;
    shadowW?: number;
    actorId?: string;
    context?: Partial<ShotContext>;
  },
): { frameIndex: number; x: number; ground: number } {
  const n = opts.frames.length;
  if (!n) throw Error("drawActorWalk 需要至少一帧");
  const im = stage.images[opts.imageId];
  if (!im) throw Error(`缺少步态图集 ${opts.imageId}`);

  const totalDur = Math.max(0.2, opts.end - opts.start);
  const period = Math.max(0.4, opts.period ?? 1.8);
  const stepDur = period / n;
  const elapsed = clamp(t - opts.start, 0, totalDur);
  const finished = t >= opts.end;
  const stepCount = Math.floor(elapsed / stepDur + 1e-8);
  const frameIndex = t <= opts.start ? 0 : finished ? n - 1 : stepCount % n;
  const maxSteps = Math.max(1, Math.floor(totalDur / stepDur));
  const moveProgress = t <= opts.start ? 0 : finished ? 1 : clamp(stepCount / maxSteps);
  const worldX = mix(opts.fromX, opts.toX, moveProgress);

  const cell = opts.frames[frameIndex];
  const [sx, sy, sw, sh] = cell.rect;
  const [ox, oy] = cell.origin;
  const [bx0, by0, bx1, by1] = cell.contentBounds ?? [0, 0, sw, sh];
  const scale = opts.pixelsPerCm / Math.max(1e-4, opts.sourcePixelsPerCm);
  const sourceFacesRight = opts.sourceFacesRight ?? true;
  const movingRight = opts.toX >= opts.fromX;
  const flip = sourceFacesRight !== movingRight;
  const opacity = opts.opacity ?? 1;

  contactShadow(stage, worldX, opts.ground + 3, opts.shadowW ?? 60, 12, 0.35, opacity);
  const g = stage.g;
  g.save();
  g.translate(worldX, opts.ground);
  g.scale(flip ? -scale : scale, scale);
  g.globalAlpha *= opacity;
  stage.shadow(opts.lift ?? 2);
  g.drawImage(im, sx, sy, sw, sh, -ox, -oy, sw, sh);
  stage.bounds({
    x: bx0 - ox,
    y: by0 - oy,
    w: Math.max(1, bx1 - bx0),
    h: Math.max(1, by1 - by0),
    name: `${opts.imageId}:frame-${frameIndex}`,
  });
  g.restore();

  recordActorState(
    opts.context,
    opts.actorId ?? "presenter",
    opts.imageId,
    cell.name || `walk-${frameIndex}`,
    "actor_walk_step",
    t,
    moveProgress,
  );

  return { frameIndex, x: worldX, ground: opts.ground };
}

/**
 * Draw a close-up disembodied forearm/hand cutout sliding smoothly from a canvas edge so the
 * cut cuff end stays hidden outside the stage border (never exposing a floating severed arm).
 */
export function drawActorEdgeHand(
  stage: Stage,
  t: number,
  opts: {
    imageId: string;
    reachX: number;
    y: number;
    start: number;
    edge?: "left" | "right";
    sourceEdge?: "left" | "right";
    width?: number;
    duration?: number;
    retreatAt?: number;
    retreatDuration?: number;
    rotation?: number;
    spanOrBeat: number | Pick<Beat, "start" | "end">;
    seed?: number;
    lift?: number;
    opacity?: number;
    actorId?: string;
    context?: Partial<ShotContext>;
  },
): { tipX: number; cuffX: number; extension: number } {
  const im = stage.images[opts.imageId];
  const asset = stage.assets[opts.imageId] as
    | { visible_bounds?: { x: number; y: number; w: number; h: number } }
    | undefined;
  if (!im) throw Error(`缺少近景手部纸件 ${opts.imageId}`);
  const vb = asset?.visible_bounds ?? { x: 0, y: 0, w: 1, h: 1 };
  const edge = opts.edge ?? "left";
  const sourceEdge = opts.sourceEdge ?? "left";
  const flip = edge !== sourceEdge;
  const minSafeSpan = edge === "left" ? opts.reachX + 24 : stage.width - opts.reachX + 24;
  const visibleW = Math.max(opts.width ?? minSafeSpan, minSafeSpan);
  const fullW = visibleW / Math.max(0.1, vb.w);
  const fullH = (fullW * im.height) / Math.max(1, im.width);

  const dt = t - opts.start;
  let ext = 0;
  if (dt > 0) {
    const enterEase = springEase(dt, SPRING.paper.stiffness, SPRING.paper.damping);
    ext = clamp(enterEase, 0, 1.04);
    if (opts.retreatAt !== undefined && t > opts.retreatAt) {
      const retDur = Math.max(0.15, opts.retreatDuration ?? 0.45);
      const retP = phase(t, opts.retreatAt, opts.retreatAt + retDur);
      ext *= 1 - retP;
    }
  }
  const baseAlpha = (opts.opacity ?? 1) * clamp(ext * 4);
  if (baseAlpha <= 0.02) {
    const parkedTip = edge === "left" ? -16 : stage.width + 16;
    return { tipX: parkedTip, cuffX: parkedTip, extension: 0 };
  }

  const cad = actorCadence(t, opts.spanOrBeat, {
    seed: opts.seed ?? 51,
    ampY: 1.1,
    ampRot: 0.003,
  });
  const rot = (opts.rotation ?? 0) + cad.rotation;
  const tipX =
    edge === "left"
      ? mix(-18, opts.reachX, ext) + cad.dx
      : mix(stage.width + 18, opts.reachX, ext) + cad.dx;
  const cuffX = edge === "left" ? tipX - visibleW : tipX + visibleW;
  const drawY = opts.y + cad.dy;

  const visLeftNorm = vb.x;
  const visRightNorm = vb.x + vb.w;
  const anchorX = sourceEdge === "right" ? -visLeftNorm * fullW : -visRightNorm * fullW;
  const boundsX = sourceEdge === "right" ? 0 : -visibleW;
  const visMidYNorm = vb.y + vb.h * 0.5;
  const g = stage.g;
  g.save();
  g.translate(tipX, drawY);
  g.rotate(rot);
  if (flip) g.scale(-1, 1);
  g.globalAlpha *= baseAlpha;
  stage.shadow(opts.lift ?? 4);
  g.drawImage(im, anchorX, -visMidYNorm * fullH, fullW, fullH);
  stage.bounds({
    x: boundsX,
    y: (-vb.h * fullH) / 2,
    w: visibleW,
    h: vb.h * fullH,
    name: opts.imageId,
  });
  g.restore();

  recordActorState(
    opts.context,
    opts.actorId ?? "presenter",
    opts.imageId,
    edge === "left" ? "edge_hand_left" : "edge_hand_right",
    "actor_edge_hand",
    t,
    clamp(ext),
  );

  return { tipX, cuffX, extension: clamp(ext) };
}

type SequenceCellInput = {
  name?: string;
  rect: readonly number[];
  origin: readonly number[];
  contentBounds?: readonly number[];
  content_bounds?: readonly number[];
};

type SequenceAtlasInput = {
  imageId?: string;
  image_id?: string;
  defaultCell?: string;
  default_cell?: string;
  blinkCell?: string;
  blink_cell?: string;
  cells?: Record<string, SequenceCellInput>;
  actor_atlas?: {
    imageId?: string;
    image_id?: string;
    defaultCell?: string;
    default_cell?: string;
    blinkCell?: string;
    blink_cell?: string;
    cells?: Record<string, SequenceCellInput>;
  };
};

function tuple4(
  v: readonly number[],
  fallback: readonly [number, number, number, number],
): readonly [number, number, number, number] {
  return v.length >= 4 ? [v[0], v[1], v[2], v[3]] : fallback;
}

function tuple2(
  v: readonly number[],
  fallback: readonly [number, number],
): readonly [number, number] {
  return v.length >= 2 ? [v[0], v[1]] : fallback;
}

/**
 * Convert an imported motion-package `sequence.json` (whose JSON arrays infer as `number[]`)
 * into a strongly-typed `ActorAtlasSpec` for `drawActorAtlas`.
 */
export function atlasFromSequence(sequence: SequenceAtlasInput, imageId?: string): ActorAtlasSpec {
  const raw = sequence.actor_atlas ?? sequence;
  const cells: Record<string, AtlasCell> = {};
  for (const [key, cell] of Object.entries(raw.cells ?? {})) {
    const rect = tuple4(cell.rect ?? [], [0, 0, 1, 1]);
    const cb = cell.contentBounds ?? cell.content_bounds;
    cells[key] = {
      name: cell.name || key,
      rect,
      origin: tuple2(cell.origin ?? [], [rect[2] / 2, rect[3]]),
      ...(cb && cb.length >= 4 ? { contentBounds: tuple4(cb, [0, 0, rect[2], rect[3]]) } : {}),
    };
  }
  const resolvedId = imageId ?? raw.imageId ?? raw.image_id ?? "";
  if (!resolvedId) {
    throw Error("atlasFromSequence 需要指定 imageId");
  }
  return {
    imageId: resolvedId,
    defaultCell: raw.defaultCell ?? raw.default_cell,
    blinkCell: raw.blinkCell ?? raw.blink_cell,
    cells,
  };
}

/**
 * Draw a solid foreground consultation desk flush with the bottom of the frame,
 * pairing naturally with waist-up `drawActorAtlas` busts so no hollow leg opening appears.
 */
export function drawForegroundDesk(
  stage: Stage,
  opts: {
    assetId?: string;
    topY?: number;
    overscanX?: number;
    bottomOverscan?: number;
    opacity?: number;
    recordBackdropBounds?: boolean;
  } = {},
): { topY: number; clipBottomY: number } {
  const assetId = opts.assetId ?? "bg_foreground_desk";
  const topY = opts.topY ?? 508;
  const overscanX = opts.overscanX ?? 48;
  const bottomOverscan = opts.bottomOverscan ?? 16;
  const opacity = opts.opacity ?? 1;
  const im = stage.images[assetId];
  if (!im) throw Error(`缺少前景实心问诊桌资源 ${assetId}`);
  const meta = stage.assets[assetId] as
    | { visible_bounds?: { x?: number; y?: number; w?: number; h?: number } }
    | undefined;
  const vb = meta?.visible_bounds;
  const sx = im.width * (vb?.x ?? 0);
  const sy = im.height * (vb?.y ?? 0.5);
  const sw = Math.max(1, im.width * (vb?.w ?? 1));
  const sh = Math.max(1, im.height - sy);
  const dx = -overscanX;
  const dw = stage.width + overscanX * 2;
  const dh = Math.max(40, stage.height + bottomOverscan - topY);

  const prevTracking = stage.tracking;
  if (!opts.recordBackdropBounds) {
    stage.tracking = false;
  }
  try {
    const g = stage.g;
    g.save();
    g.globalAlpha *= opacity;
    g.drawImage(im, sx, sy, sw, sh, dx, topY, dw, dh);
    if (opts.recordBackdropBounds) {
      stage.bounds({ x: dx, y: topY, w: dw, h: dh, name: assetId });
    }
    g.restore();
  } finally {
    stage.tracking = prevTracking;
  }

  return { topY, clipBottomY: topY + 8 };
}
