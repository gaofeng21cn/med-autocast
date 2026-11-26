import { Easing, interpolate, spring } from "remotion";
import type { Camera, Point, Pose, Score, Sound } from "./types";

const SPRING_EVAL_FPS = 60;

export const clamp = (v: number, a = 0, b = 1) =>
  a === b
    ? a
    : interpolate(v, [a, b], [a, b], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
export const mix = (a: number, b: number, p: number) =>
  interpolate(p, [0, 1], [a, b]);
export const smooth = (v: number) =>
  interpolate(v, [0, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: (p) => p * p * (3 - 2 * p),
  });
export const easeOut = (p: number) =>
  interpolate(p, [0, 1], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
export const progress = (t: number, start: number, end: number) =>
  end === start
    ? Number(t >= end)
    : interpolate(t, [start, end], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
export const phase = (t: number, start: number, end: number) =>
  smooth(progress(t, start, end));
// Strict event gate: returns 0 before `at`, preventing premature ghost reveals.
export const revealWindow = (t: number, at: number, duration = 0.28) =>
  t < at ? 0 : easeOut(progress(t, at, at + Math.max(1e-6, duration)));

// Remotion spring presets (deterministic closed-form evaluation, no frame history).
export type SpringPreset = { stiffness: number; damping: number; mass?: number };
export const SPRING = {
  snappy: { stiffness: 320, damping: 30 },
  smooth: { stiffness: 170, damping: 26 },
  heavy: { stiffness: 96, damping: 20 },
  paper: { stiffness: 220, damping: 22 },
} as const satisfies Record<string, SpringPreset>;

export function springEase(
  dt: number,
  stiffness: number = SPRING.smooth.stiffness,
  damping: number = SPRING.smooth.damping,
  mass: number = 1,
): number {
  if (dt <= 0) return 0;
  return spring({
    frame: dt * SPRING_EVAL_FPS,
    fps: SPRING_EVAL_FPS,
    config: { stiffness, damping, mass },
  });
}

export function springMove(
  t: number,
  start: number,
  from: number,
  to: number,
  preset: SpringPreset = SPRING.paper,
): number {
  return interpolate(
    springEase(t - start, preset.stiffness, preset.damping, preset.mass ?? 1),
    [0, 1],
    [from, to],
  );
}

export function springTrack(
  t: number,
  keys: readonly (readonly [number, number])[],
  preset: SpringPreset = SPRING.smooth,
): number {
  if (!keys.length) throw Error("springTrack 需要至少一个关键点");
  const sorted = [...keys].sort((a, b) => a[0] - b[0]);
  let value = sorted[0][1];
  for (let i = 1; i < sorted.length; i++) {
    value +=
      (sorted[i][1] - sorted[i - 1][1]) *
      springEase(t - sorted[i][0], preset.stiffness, preset.damping, preset.mass ?? 1);
  }
  return value;
}

// Non-exiting handoff: dims and steps back a previous subject while explicitly
// declaring that its layout slot remains occupied (distinct from true exit).
export function demotePose(
  t: number,
  demoteAt: number,
  options: { duration?: number; scaleTo?: number; liftY?: number; opacityTo?: number } = {},
): { scale: number; dy: number; opacity: number; dim: number; occupiesSlot: true } {
  const dur = Math.max(1e-6, options.duration ?? 0.45);
  const p = t < demoteAt ? 0 : smooth(progress(t, demoteAt, demoteAt + dur));
  return {
    scale: mix(1, options.scaleTo ?? 0.92, p),
    dy: mix(0, options.liftY ?? -10, p),
    opacity: mix(1, options.opacityTo ?? 0.36, p),
    dim: p,
    occupiesSlot: true,
  };
}
export const hash = (n: number) => {
  const v = Math.sin(n * 127.13 + 41.17) * 43758.5453;
  return v - Math.floor(v);
};

/** Parabolic paper-card arrival onto the desk: deterministic spring settle
 * paired with vertical lift, dynamic tilt, and a normalized `lift01` signal for shadow spread.
 */
export function landPose(
  t: number,
  start: number,
  from: Pose,
  to: Pose,
  options: { lift?: number; entryTilt?: number; preset?: SpringPreset; settleWindow?: number } = {},
): Pose & { lift01: number } {
  const preset: SpringPreset = options.preset ?? SPRING.paper;
  const dt = t - start;
  const p = dt <= 0 ? 0 : springEase(dt, preset.stiffness, preset.damping, preset.mass ?? 1);
  const win = Math.max(0.12, options.settleWindow ?? 0.55);
  const arcP = dt <= 0 ? 0 : progress(t, start, start + win);
  const lift01 = dt <= 0 || arcP >= 1 ? 0 : Math.max(0, Math.sin(Math.PI * arcP));
  return {
    x: mix(from.x, to.x, p),
    y: mix(from.y, to.y, p) - (options.lift ?? 26) * lift01,
    rotation: mix(from.rotation ?? 0, to.rotation ?? 0, p) + (options.entryTilt ?? 0.045) * lift01,
    scale: mix(from.scale ?? 1, to.scale ?? 1, p),
    ...(from.opacity !== undefined || to.opacity !== undefined
      ? { opacity: mix(from.opacity ?? 1, to.opacity ?? 1, p) }
      : {}),
    lift01,
  };
}

/** Subtle organic breathing offset for settled paper pieces without jittering the stage.
 * Pass `settleBefore` (with optional `fadeWindow`) to damp motion cleanly to zero before a cut.
 */
export function aliveBreath(
  t: number,
  seed = 1,
  options: { ampY?: number; ampRot?: number; hz?: number; settleBefore?: number; fadeWindow?: number } = {},
): { dx: number; dy: number; rotation: number } {
  let env = 1;
  if (options.settleBefore !== undefined) {
    if (t >= options.settleBefore) return { dx: 0, dy: 0, rotation: 0 };
    const win = Math.max(0.05, options.fadeWindow ?? 0.6);
    const fadeStart = options.settleBefore - win;
    if (t > fadeStart) {
      env = 1 - smooth(phase(t, fadeStart, options.settleBefore));
    }
  }
  const phi = hash(seed) * Math.PI * 2;
  const w = t * Math.PI * 2 * (options.hz ?? 0.42) + phi;
  const ampY = (options.ampY ?? 2.2) * env;
  const ampRot = (options.ampRot ?? 0.011) * env;
  return {
    dx: Math.cos(w * 0.7) * (ampY * 0.35),
    dy: Math.sin(w) * ampY,
    rotation: Math.sin(w * 0.85 + 0.6) * ampRot,
  };
}

/** Shot-aware breathing that fades smoothly to exact zero before the 15/16 tail sample (`pose11`). */
export function settledBreath(
  t: number,
  span: number,
  seed = 1,
  options: { ampY?: number; ampRot?: number; hz?: number; tailMargin?: number; fadeWindow?: number } = {},
): { dx: number; dy: number; rotation: number } {
  const margin = Math.max(0.2, options.tailMargin ?? 1.6);
  return aliveBreath(t, seed, {
    ampY: options.ampY,
    ampRot: options.ampRot,
    hz: options.hz,
    settleBefore: Math.max(0, span - margin),
    fadeWindow: options.fadeWindow,
  });
}

/** Shot-aware breathing convenience wrapper supporting numeric span or `{ start, end }` beat. */
export function shotBreath(
  t: number,
  spanOrBeat: number | { start: number; end: number },
  seed = 1,
  options: { ampY?: number; ampRot?: number; hz?: number; tailMargin?: number; fadeWindow?: number } = {},
): { dx: number; dy: number; rotation: number } {
  const span =
    typeof spanOrBeat === "number"
      ? Math.max(0.5, spanOrBeat)
      : Math.max(0.5, spanOrBeat.end - spanOrBeat.start);
  const margin = Math.max(options.tailMargin ?? 1.65, span * 0.17);
  return settledBreath(t, span, seed, { ...options, tailMargin: margin });
}

/** Discrete stepped index with phase offset to keep global progress/calendar switches clear of shot cuts. */
export function phaseShiftStep(progress01: number, steps: number, offset = 0.25): number {
  const count = Math.max(1, Math.floor(steps));
  return Math.min(count - 1, Math.max(0, Math.floor(clamp(progress01) * count + offset)));
}
// Damped ring-down shared by clips and dropped sheets. `tracks.settle` re-exports
// the same curve; it lives here so action solvers stay free of a cycle.
const ringDown = (t: number, contact: number, amplitude: number, decay: number, hz: number) => {
  const dt = t - contact;
  return dt < 0 ? 0 : amplitude * Math.exp(-decay * dt) * Math.sin(dt * Math.PI * 2 * hz);
};
export function arc(from: Point, to: Point, p: number, lift = 30): Point {
  return {
    x: mix(from.x, to.x, p),
    y: mix(from.y, to.y, p) - Math.sin(Math.PI * p) * lift,
  };
}
// Objects may sample poses on twos; audio and the camera retain the master clock.
export const onTwos = (t: number, fps = 24) =>
  (Math.floor((t * fps) / 2) * 2) / fps;
export function stow(
  t: number,
  start: number,
  end: number,
  from: Pose,
  to: Pose,
): Pose {
  const p = phase(t, start, end);
  return {
    ...arc(from, to, p, 34),
    rotation: mix(from.rotation || 0, to.rotation || 0, p),
    scale: mix(from.scale || 1, to.scale || 1, p),
  };
}
export function stampPose(
  t: number,
  contact: number,
  lift: number,
  target: Point,
): Pose & { height: number; printed: boolean } {
  const down = phase(t, contact - 0.78, contact),
    up = phase(t, lift, lift + 0.85);
  const height = (1 - down) * 190 + up * 660;
  return {
    x: target.x + (1 - down) * 95 + up * 155,
    y: target.y - height,
    rotation: (1 - down) * 0.14 + up * 0.13,
    height,
    printed: t >= contact - 1e-9,
  };
}

// ---------------------------------------------------------------------------
// Paper action vocabulary
//
// These are pose/reveal solvers only. They hold no story, no disease and no
// composition, so a single-episode director can reuse them without inheriting a
// fixed shot. Every solver is a pure function of time: random seeks and reverse
// seeks return the same pose.
// ---------------------------------------------------------------------------

// Peeling/lifting: the piece rises, tilts toward the viewer and lands. Used for
// lifting a label, opening a flap or picking up a card off a stack.
export function liftPose(
  t: number,
  start: number,
  peak: number,
  end: number,
  from: Pose,
  to: Pose,
  lift = 26,
): Pose & { lift01: number } {
  // Rising and travelling are separate phases: the piece leaves the surface at
  // `peak` and only then travels to `to`. Collapsing them made the lift read as
  // a slide instead of a pick-up.
  const up = phase(t, start, peak),
    down = phase(t, peak, end),
    // Triangular lift: high at `peak`, zero at both ends, so the peak frame
    // always reads as the piece being off the surface.
    rise = up < 1 ? up : 1 - down,
    travel = down,
    fall = easeOut(travel);
  return {
    x: mix(from.x, to.x, fall),
    y: mix(from.y, to.y, fall) - rise * lift,
    rotation: mix(from.rotation || 0, to.rotation || 0, easeOut(fall)),
    scale: mix(from.scale ?? 1, to.scale ?? 1, easeOut(fall)),
    opacity: mix(from.opacity ?? 1, to.opacity ?? 1, rise),
    lift01: rise,
  };
}

// A tear separates along an authored line. `closed` is the intact sheet; the
// two halves drift apart with a small opposite rotation. Fibres are drawn by
// the caller from the same `edge` value so the seam stays coherent.
export function tearPose(
  t: number,
  start: number,
  end: number,
  axis: "v" | "h" = "v",
): { amount: number; left: Pose; right: Pose } {
  const p = easeOut(phase(t, start, end));
  const gap = p * 46;
  return axis === "v"
    ? {
        amount: p,
        left: { x: -gap, y: p * 2, rotation: -p * 0.045 },
        right: { x: gap, y: -p * 1.5, rotation: p * 0.05 },
      }
    : {
        amount: p,
        left: { x: -p * 2, y: -gap, rotation: -p * 0.04 },
        right: { x: p * 1.5, y: gap, rotation: p * 0.045 },
      };
}

// A fold closes a panel over its content. `openness` 1 is flat, 0 is folded
// shut. The caller draws the crease and the shaded inner face.
export function foldPose(
  t: number,
  start: number,
  end: number,
  from = 1,
  to = 0,
): { openness: number; crease: number; squash: number } {
  const openness = mix(from, to, smooth(phase(t, start, end))),
    p = 1 - openness;
  return {
    openness,
    crease: Math.sin(p * Math.PI) * 0.9,
    squash: Math.cos(p * Math.PI * 0.5),
  };
}

// Turning a page lifts the corner before the sheet crosses the spine. The
// returned pose drives a horizontal squash plus a shadow, so the page reads as
// bending paper rather than sliding a rectangle.
export function pageTurn(
  t: number,
  start: number,
  end: number,
): { progress: number; corner: number; bend: number; flip: number } {
  const p = smooth(phase(t, start, end));
  return {
    progress: p,
    corner: Math.sin(p * Math.PI),
    bend: Math.sin(p * Math.PI) * 0.34,
    flip: p < 0.5 ? -p * 2 : (p - 1) * 2,
  };
}

// Pulling a strip out of a holder (test tube, measuring cup, sleeve). The
// object keeps its angle while travelling along `axis`; `exposure` tells the
// caller how much of the content should be visible.
export function drawOut(
  t: number,
  start: number,
  end: number,
  distance: number,
  axis: "x" | "y" = "y",
): { amount: number; pose: Pose; exposure: number } {
  const p = smooth(phase(t, start, end));
  const travel = p * distance;
  return {
    amount: p,
    pose: axis === "y"
      ? { x: 0, y: -travel, rotation: p * 0.05 }
      : { x: travel, y: 0, rotation: -p * 0.04 },
    exposure: Math.sin(p * Math.PI * 0.5),
  };
}

// A measuring tape or rolled strip extends and can be read at the tip.
export function unroll(
  t: number,
  start: number,
  end: number,
  length: number,
): { amount: number; length: number; curl: number } {
  const p = smooth(phase(t, start, end));
  return {
    amount: p,
    length: p * length,
    curl: (1 - p) * Math.min(1, length / 90),
  };
}

// Wrapping turns a band around a subject. `wrap01` is 0 (untouched) to 1
// (fully banded); the caller draws the band with the same fraction so cloth,
// tape and gauze share one solver.
export function wrapBand(
  t: number,
  start: number,
  end: number,
  turns = 1,
): { wrap01: number; turns: number; tension: number } {
  const p = smooth(phase(t, start, end));
  return { wrap01: p, turns: p * turns, tension: Math.sin(p * Math.PI) };
}

// Cutting follows an authored path: the blade travels, then the two parts
// separate. Returned `severed` is the moment the cut completes, so a sound cue
// can share the same event time.
export function cutAlong(
  t: number,
  start: number,
  severAt: number,
  end: number,
): { progress: number; severed: boolean; blade: number; spread: number } {
  const progress = easeOut(phase(t, start, severAt)),
    after = smooth(phase(t, severAt, end));
  return {
    progress,
    severed: t >= severAt,
    blade: progress,
    spread: after,
  };
}

// A pen or finger traces a measured path. The caller draws with `trace()`; this
// only reports how far the stroke has run and whether the nib has lifted.
export function strokeAlong(
  t: number,
  start: number,
  end: number,
  hold = 0,
): { fraction: number; drawing: boolean; penDown: boolean; speed: number } {
  const p = progress(t, start + hold, end),
    q = smooth(p);
  return {
    fraction: q,
    drawing: t >= start + hold && t < end,
    penDown: t >= start + hold,
    speed: t > start + hold && t <= end ? 6 * q * (1 - q) : 0,
  };
}

// A clip or tong snaps shut. The small overshoot is what makes a fastener read
// as mechanical rather than as a fade.
export function clipSnap(
  t: number,
  closeAt: number,
  openWidth = 1,
): { gap: number; shut: boolean; recoil: number } {
  const close = easeOut(phase(t, closeAt - 0.28, closeAt)),
    recoil = t >= closeAt ? ringDown(t, closeAt, 0.22, 9, 4) : 0;
  return {
    gap: mix(openWidth, 0, close) + recoil,
    shut: t >= closeAt,
    recoil,
  };
}

// A dropped sheet falls, lands and rings down. `impact` is the landing time.
export function dropSettle(
  t: number,
  release: number,
  impact: number,
  from: Point,
  to: Point,
): Pose & { height: number; landed: boolean } {
  const fall = easeOut(phase(t, release, impact)),
    ring = t >= impact ? ringDown(t, impact, 1, 7, 3.4) : 0;
  return {
    x: mix(from.x, to.x, fall) + ring * 2.4,
    y: mix(from.y, to.y, fall) - Math.sin(Math.PI * fall) * 42,
    rotation: ring * 0.05,
    scale: 1 - Math.abs(ring) * 0.035,
    height: Math.sin(Math.PI * clamp(fall)),
    landed: t >= impact,
  };
}

// A map or board opens in stages. `panels` returns how many leaves are open so
// the caller can stagger them instead of scaling one rectangle.
export function unfoldPanels(
  t: number,
  start: number,
  end: number,
  panels: number,
): { open: number[]; total: number } {
  const total = smooth(phase(t, start, end));
  const open = Array.from({ length: panels }, (_, i) =>
    smooth(clamp((total - i * (0.55 / panels)) * (panels / 0.55))),
  );
  return { open, total };
}

// Paper breathing: a tiny, decaying asymmetry used only for hand-made
// irregularity. It must never be applied to anatomy, captions or a whole layer.
export function handmade(
  t: number,
  seed: number,
  amplitude = 0.004,
): { dx: number; dy: number; drot: number } {
  return {
    dx: (hash(seed + Math.floor(t * 3)) - 0.5) * amplitude * 2,
    dy: (hash(seed + 61 + Math.floor(t * 3)) - 0.5) * amplitude,
    drot: (hash(seed + 97 + Math.floor(t * 3)) - 0.5) * amplitude,
  };
}

// Camera moves. These return a camera target for one shot; the director owns
// when a shot pushes in, pans with an object or drifts. Amounts are relative.
export function pushIn(
  t: number,
  start: number,
  end: number,
  from = 1,
  to = 1.22,
  target: Point = { x: 640, y: 306 },
): Camera {
  const p = smooth(phase(t, start, end));
  return { x: mix(640, target.x, p), y: mix(306, target.y, p), zoom: mix(from, to, p) };
}
export function panWith(
  t: number,
  start: number,
  end: number,
  from: Point,
  to: Point,
  zoom = 1,
): Camera {
  const p = smooth(phase(t, start, end));
  return { x: mix(from.x, to.x, p), y: mix(from.y, to.y, p), zoom };
}
export function pullOut(
  t: number,
  start: number,
  end: number,
  from = 1.24,
  to = 1,
  target: Point = { x: 640, y: 306 },
): Camera {
  return pushIn(t, start, end, from, to, target);
}
export function tiltDrift(
  t: number,
  start: number,
  end: number,
  degrees = 2.4,
): Camera {
  const p = smooth(phase(t, start, end));
  return {
    x: 640 + Math.sin(p * Math.PI) * 9,
    y: 306 + Math.sin(p * Math.PI * 0.7) * 5,
    zoom: 1 + p * 0.012,
    rotation: (degrees * Math.PI / 180) * Math.sin(p * Math.PI),
  };
}

// Focus a world point onto a chosen screen offset (relative to Stage.camera's
// default focus center `(640, 306)`), so zooming in never pushes subjects into
// the lower subtitle band or over a co-present presenter.
export function focusOn(
  t: number,
  start: number,
  end: number,
  from: Camera,
  worldTarget: Point,
  zoomTo: number,
  screenOffset: Point = { x: 0, y: 0 },
): Camera {
  const p = smooth(phase(t, start, end));
  const safeZoom = Math.max(1e-3, zoomTo);
  const targetCamX = worldTarget.x - screenOffset.x / safeZoom;
  const targetCamY = worldTarget.y - screenOffset.y / safeZoom;
  return {
    x: mix(from.x, targetCamX, p),
    y: mix(from.y, targetCamY, p),
    zoom: mix(from.zoom, safeZoom, p),
    rotation: mix(from.rotation || 0, 0, p),
  };
}

// Constant-velocity subtle push/pull that never stalls to zero speed before a cut.
export function gentleDrift(
  t: number,
  start: number,
  end: number,
  fromZoom = 1,
  toZoom = 1.045,
  target: Point = { x: 640, y: 306 },
): Camera {
  const p = progress(t, start, end);
  return {
    x: target.x,
    y: target.y,
    zoom: mix(fromZoom, toZoom, p),
  };
}
export function soundTime(score: Score, event: Sound): number {
  const shot = score.shots.find((s) => s.id === event.shot);
  if (!shot || shot.events[event.event] === undefined)
    throw Error(`声音引用未知事件 ${event.shot}.${event.event}`);
  return shot.start + shot.events[event.event] + (event.offset || 0);
}
