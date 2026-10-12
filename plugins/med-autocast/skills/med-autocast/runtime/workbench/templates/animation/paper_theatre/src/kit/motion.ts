import type { Camera, Point, Pose, Score, Sound } from "./types";
export const clamp = (v: number, a = 0, b = 1) => Math.max(a, Math.min(b, v));
export const mix = (a: number, b: number, p: number) => a + (b - a) * p;
export const smooth = (v: number) => {
  const p = clamp(v);
  return p * p * (3 - 2 * p);
};
export const easeOut = (p: number) => 1 - (1 - clamp(p)) ** 3;
export const progress = (t: number, start: number, end: number) =>
  end === start ? Number(t >= end) : clamp((t - start) / (end - start));
export const phase = (t: number, start: number, end: number) =>
  smooth(progress(t, start, end));
export const hash = (n: number) => {
  const v = Math.sin(n * 127.13 + 41.17) * 43758.5453;
  return v - Math.floor(v);
};
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
export function soundTime(score: Score, event: Sound): number {
  const shot = score.shots.find((s) => s.id === event.shot);
  if (!shot || shot.events[event.event] === undefined)
    throw Error(`声音引用未知事件 ${event.shot}.${event.event}`);
  return shot.start + shot.events[event.event] + (event.offset || 0);
}
