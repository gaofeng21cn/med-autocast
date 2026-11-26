import type { Stage } from "./stage";
import type { Beat, ShotContext } from "./types";
import { actorCadence, type CueSpan } from "./actor";
import { clamp } from "./motion";
import { contactShadow } from "./staging";

export type MicroPatchSpec = {
  imageId: string;
  x: number;
  y: number;
  w: number;
  h: number;
};

export type MicroActorRigSpec = {
  id: string;
  baseImageId: string;
  baseSize: readonly [number, number];
  origin: readonly [number, number];
  contentBounds?: readonly [number, number, number, number];
  eyes: {
    open?: MicroPatchSpec;
    closed: MicroPatchSpec;
    glanceLeft?: MicroPatchSpec;
    glanceRight?: MicroPatchSpec;
  };
  mouths: {
    closed?: MicroPatchSpec;
    softOpen: MicroPatchSpec;
    midOpen?: MicroPatchSpec;
  };
};

export type EyePoseName = "open" | "closed" | "glanceLeft" | "glanceRight";
export type MouthPoseName = "closed" | "softOpen" | "midOpen";

export type GazeBeat = {
  at: number;
  eye: "open" | "glanceLeft" | "glanceRight";
  triggerBlink?: boolean;
};

export type SpeechEnvelope = {
  fps: number;
  duration_s?: number;
  values: readonly number[];
};

function tailStopTime(span: number, tailMargin?: number): number {
  const margin = Math.max(tailMargin ?? 0.35, Math.min(0.85, span * 0.1));
  return Math.max(0.2, span - margin);
}

/**
 * Solve calm, non-jittery mouth viseme state from a 24fps speech RMS envelope.
 * Applies hysteresis thresholds, a minimum hold window (~95ms) to prevent 1-frame flutter,
 * and clamps cleanly to `"closed"` at the end of a shot.
 */
export function sampleSpeechMouth(
  t: number,
  envelope: SpeechEnvelope | undefined,
  opts: {
    span?: number;
    softThreshold?: number;
    midThreshold?: number;
    minHoldSec?: number;
    tailMargin?: number;
  } = {},
): MouthPoseName {
  if (!envelope || !envelope.values.length) return "closed";
  const fps = Math.max(1, envelope.fps || 24);
  const span = opts.span ?? envelope.duration_s ?? envelope.values.length / fps;
  const stopAt = tailStopTime(span, opts.tailMargin);
  if (t < 0 || t >= stopAt) return "closed";

  const softTh = opts.softThreshold ?? 0.14;
  const midTh = opts.midThreshold ?? 0.44;
  const hyst = 0.04;
  const minHoldFrames = Math.max(1, Math.round((opts.minHoldSec ?? 0.095) * fps));
  const targetIdx = Math.min(envelope.values.length - 1, Math.max(0, Math.floor(t * fps)));

  let state: MouthPoseName = "closed";
  let lastSwitchIdx = -minHoldFrames;

  for (let i = 0; i <= targetIdx; i++) {
    const v = envelope.values[i] ?? 0;
    let desired: MouthPoseName = state;
    if (state === "closed") {
      if (v >= midTh) desired = "midOpen";
      else if (v >= softTh) desired = "softOpen";
    } else if (state === "softOpen") {
      if (v >= midTh) desired = "midOpen";
      else if (v < softTh - hyst) desired = "closed";
    } else {
      if (v < softTh - hyst) desired = "closed";
      else if (v < midTh - hyst) desired = "softOpen";
    }

    if (desired !== state && i - lastSwitchIdx >= minHoldFrames) {
      state = desired;
      lastSwitchIdx = i;
    }
  }

  return state;
}

/**
 * Resolve deterministic eye orientation and single natural physiological blinks
 * (for example, right as gaze shifts from an object toward the viewer), settling open at shot end.
 */
export function solveEyeState(
  t: number,
  gazeBeats: readonly GazeBeat[] | undefined,
  opts: {
    span: number;
    blinkTimes?: readonly number[];
    blinkDuration?: number;
    tailMargin?: number;
  },
): { eye: EyePoseName; isBlinking: boolean } {
  const stopAt = tailStopTime(opts.span, opts.tailMargin);
  const sorted = gazeBeats?.length ? [...gazeBeats].sort((a, b) => a.at - b.at) : [];

  const blinks = new Set<number>(opts.blinkTimes ?? []);
  for (const b of sorted) {
    if (b.triggerBlink) blinks.add(Math.max(0.08, b.at - 0.06));
  }

  const dur = clamp(opts.blinkDuration ?? 0.092, 0.075, 0.22);
  let isBlinking = false;
  if (t < stopAt - 0.1) {
    for (const bt of blinks) {
      if (t >= bt && t < bt + dur) {
        isBlinking = true;
        break;
      }
    }
  }

  if (t >= stopAt) {
    return { eye: sorted.length ? sorted[sorted.length - 1].eye : "open", isBlinking: false };
  }
  if (isBlinking) {
    return { eye: "closed", isBlinking: true };
  }

  let activeEye: EyePoseName = "open";
  for (const b of sorted) {
    if (t >= b.at) activeEye = b.eye;
    else break;
  }
  return { eye: activeEye, isBlinking: false };
}

/**
 * Draw a 100%-body-locked waist-up micro-acting character by composing local feathered
 * eye and mouth patches precisely over an unchanging calibrated base portrait.
 */
export function drawMicroActor(
  stage: Stage,
  t: number,
  opts: {
    rig: MicroActorRigSpec;
    x: number;
    y: number;
    width: number;
    spanOrBeat: number | Pick<Beat, "start" | "end">;
    cues?: readonly CueSpan[];
    gazeBeats?: readonly GazeBeat[];
    blinkTimes?: readonly number[];
    speech?: SpeechEnvelope;
    clipBottomY?: number;
    seed?: number;
    opacity?: number;
    lift?: number;
    shadowW?: number;
    actorId?: string;
    context?: Partial<ShotContext>;
  },
): { eye: EyePoseName; mouth: MouthPoseName; x: number; y: number } {
  const span =
    typeof opts.spanOrBeat === "number"
      ? Math.max(0.5, opts.spanOrBeat)
      : Math.max(0.5, opts.spanOrBeat.end - opts.spanOrBeat.start);

  const cad = actorCadence(t, opts.spanOrBeat, {
    cues: opts.cues,
    seed: opts.seed ?? 23,
    ampY: 0.7,
    ampRot: 0.002,
    ampNod: 1.0,
  });

  const { eye } = solveEyeState(t, opts.gazeBeats, {
    span,
    blinkTimes: opts.blinkTimes,
  });
  const mouth = sampleSpeechMouth(t, opts.speech, { span });

  const baseImg = stage.images[opts.rig.baseImageId];
  if (!baseImg) throw Error(`缺少微动角色底座素材 ${opts.rig.baseImageId}`);

  const [bw, bh] = opts.rig.baseSize;
  const [ox, oy] = opts.rig.origin;
  const [bx0, by0, bx1, by1] = opts.rig.contentBounds ?? [0, 0, bw, bh];
  const scale = opts.width / Math.max(1, bw);
  const opacity = opts.opacity ?? 1;
  if (opacity <= 0.02) {
    return { eye, mouth, x: opts.x, y: opts.y };
  }

  const eyePatch =
    eye === "closed"
      ? opts.rig.eyes.closed
      : eye === "glanceLeft"
        ? opts.rig.eyes.glanceLeft
        : eye === "glanceRight"
          ? opts.rig.eyes.glanceRight
          : opts.rig.eyes.open;

  const mouthPatch =
    mouth === "midOpen"
      ? opts.rig.mouths.midOpen ?? opts.rig.mouths.softOpen
      : mouth === "softOpen"
        ? opts.rig.mouths.softOpen
        : opts.rig.mouths.closed;

  const drawBody = () => {
    const g = stage.g;
    const drawX = opts.x + cad.dx;
    const drawY = opts.y + cad.dy;
    if ((opts.shadowW ?? 0) > 0 && opts.clipBottomY !== undefined) {
      contactShadow(stage, drawX, opts.clipBottomY + 2, opts.shadowW ?? 90, 14, 0.28, opacity);
    }
    g.save();
    g.translate(drawX, drawY);
    g.rotate(cad.rotation);
    g.scale(scale, scale);
    g.globalAlpha *= opacity;
    stage.shadow(opts.lift ?? 2);

    // 1. 100%-locked base body/hair/glasses/coat
    g.drawImage(baseImg, 0, 0, bw, bh, -ox, -oy, bw, bh);

    // 2. Local feathered facial patches aligned directly to base pixels (no double drop-shadow)
    stage.shadow(0);
    if (eyePatch && stage.images[eyePatch.imageId]) {
      g.drawImage(
        stage.images[eyePatch.imageId],
        eyePatch.x - ox,
        eyePatch.y - oy,
        eyePatch.w,
        eyePatch.h,
      );
    }
    if (mouthPatch && stage.images[mouthPatch.imageId]) {
      g.drawImage(
        stage.images[mouthPatch.imageId],
        mouthPatch.x - ox,
        mouthPatch.y - oy,
        mouthPatch.w,
        mouthPatch.h,
      );
    }

    stage.bounds({
      x: bx0 - ox,
      y: by0 - oy,
      w: Math.max(1, bx1 - bx0),
      h: Math.max(1, by1 - by0),
      name: `${opts.rig.id}:${eye}_${mouth}`,
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

  const perf = (opts.context as { performanceStates?: unknown[] } | undefined)?.performanceStates;
  if (Array.isArray(perf)) {
    perf.push({
      actor_id: opts.actorId ?? "presenter",
      asset_id: opts.rig.id,
      pose: `${eye}:${mouth}`,
      event: "micro_acting",
      elapsed: t,
      transition: 1,
    });
  }

  return { eye, mouth, x: opts.x, y: opts.y };
}
