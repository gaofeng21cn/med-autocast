import type { Pose } from "./types";
import { Stage } from "./stage";
import { phase } from "./motion";

/**
 * Choreography skeletons.
 *
 * A shot stops reading as a slide the moment it has a dramatic arc: something
 * arrives, does work, causes a reaction, and settles. Writing that arc by hand
 * for several hundred shots invites three failures — the arc gets skipped, the
 * timing drifts away from the narration, and every scene ends up with the same
 * beat count.
 *
 * These helpers own only the *timing and pose* of an arc. The director supplies
 * the artwork. That split is what lets a whole series share a floor without any
 * two scenes looking alike.
 */

export type ArcPhase = "enter" | "work" | "react" | "settle";

export type Arc = {
  phase: ArcPhase;
  /** 0..1 progress inside that beat */
  u: number;
  /** overall 0..1 progress, for callers that need a single ramp */
  total: number;
  /** pose for an object that travels from off-frame to its mark */
  enter: Pose;
  /** small settle offset that decays to zero — the "weight" of contact */
  settle: Pose;
  /** true once the arc has finished; use it to hold a readable final state */
  done: boolean;
};

export type ArcSpec = {
  enter?: [number, number];
  work?: [number, number];
  react?: [number, number];
  settle?: [number, number];
  from?: { x: number; y: number };
  to?: { x: number; y: number };
  scale?: number;
  turn?: number;
};

/** Build the canonical enter → work → react → settle arc. */
export function arc(t: number, spec: ArcSpec = {}): Arc {
  const e = spec.enter ?? [0.15, 1.15];
  const w = spec.work ?? [e[1], e[1] + 1.9];
  const r = spec.react ?? [w[1], w[1] + 1.1];
  const s = spec.settle ?? [r[1], r[1] + 1.4];

  const from = spec.from ?? { x: 1180, y: 300 };
  const to = spec.to ?? { x: 640, y: 320 };
  const startScale = spec.scale ?? 0.86;
  const turn = spec.turn ?? 0.06;

  const smooth = (a: number, b: number) => {
    const u = phase(t, a, b);
    return u * u * (3 - 2 * u);
  };
  const inU = phase(t, e[0], e[1]);
  const wU = phase(t, w[0], w[1]);
  const rU = phase(t, r[0], r[1]);
  const sU = phase(t, s[0], s[1]);
  const travel = smooth(e[0], e[1]);
  const settleDecay = 1 - phase(t, r[0], s[1]);

  const phaseName: ArcPhase =
    t < w[0] ? "enter" : t < r[0] ? "work" : t < s[0] ? "react" : "settle";
  const u =
    phaseName === "enter" ? inU : phaseName === "work" ? wU : phaseName === "react" ? rU : sU;

  const enter: Pose = {
    x: from.x + (to.x - from.x) * travel,
    y: from.y + (to.y - from.y) * travel - Math.sin(travel * Math.PI) * 18,
    scale: startScale + (1 - startScale) * travel,
    rotation: turn * (1 - travel),
  };
  const settle: Pose = {
    x: 0,
    y: (1 - settleDecay) * 3.5,
    rotation: (1 - settleDecay) * 0.008,
    opacity: 0.35 + 0.65 * settleDecay,
  };

  return {
    phase: phaseName,
    u,
    total: phase(t, e[0], s[1]),
    enter,
    settle,
    done: t >= s[0],
  };
}

/**
 * Unfold → reveal → compare → stow.
 *
 * Used whenever a scene owns a container whose contents must be *discovered*
 * rather than announced. The compare beat is the one that earns the shot: two
 * things must be visible at once before one of them leaves.
 */
export function unfoldRevealCompareStow(
  t: number,
  windows: {
    unfold?: [number, number];
    reveal?: [number, number];
    compare?: [number, number];
    stow?: [number, number];
  } = {},
) {
  const u = phase(t, windows.unfold?.[0] ?? 0.2, windows.unfold?.[1] ?? 1.8);
  const r = phase(t, windows.reveal?.[0] ?? 1.6, windows.reveal?.[1] ?? 3.4);
  const c = phase(t, windows.compare?.[0] ?? 3.2, windows.compare?.[1] ?? 5.2);
  const s = phase(t, windows.stow?.[0] ?? 5.4, windows.stow?.[1] ?? 7.2);
  return {
    open: u,
    reveal: r,
    compare: c,
    stow: s,
    visible: u > 0.02,
    held: s < 0.02,
    done: t >= (windows.stow?.[0] ?? 5.4),
  };
}

/**
 * Walk → arrive → hand off.
 *
 * A person (or a document) crossing the stage is the cheapest way to make a
 * sequence feel continuous, because the travel itself carries the meaning.
 */
export function walkArriveHandoff(
  t: number,
  spec: {
    walk?: [number, number];
    arrive?: [number, number];
    hand?: [number, number];
    from?: { x: number; y: number };
    to?: { x: number; y: number };
    scale?: number;
  } = {},
) {
  const w = spec.walk ?? [0.2, 2.4];
  const a = spec.arrive ?? [2.2, 3.2];
  const h = spec.hand ?? [3.4, 5.0];
  const from = spec.from ?? { x: 1180, y: 430 };
  const to = spec.to ?? { x: 700, y: 360 };
  const startScale = spec.scale ?? 0.92;
  const walkU = phase(t, w[0], w[1]);
  const arriveU = phase(t, a[0], a[1]);
  const handU = phase(t, h[0], h[1]);
  const bob = Math.sin(t * 7.5) * 3 * (1 - arriveU);
  return {
    carrier: {
      x: from.x + (to.x - from.x) * walkU,
      y: from.y + (to.y - from.y) * walkU + bob,
      scale: startScale + (1 - startScale) * arriveU,
      rotation: 0,
    } as Pose,
    walk: walkU,
    arrive: arriveU,
    hand: handU,
    arrived: arriveU >= 0.999,
    done: t >= h[0],
  };
}

/**
 * Layered reveal for anatomy.
 *
 * Anatomy is the one place where "show everything at once" actively misleads.
 * Layers are built in the order the narration names them, so the shot always
 * has a current subject.
 */
export function layerReveal(
  t: number,
  count: number,
  spec: { start?: number; step?: number; span?: number } = {},
) {
  const start = spec.start ?? 0.6;
  const step = spec.step ?? 1.1;
  const span = spec.span ?? 0.9;
  const layers = [];
  for (let i = 0; i < count; i++) {
    const at = start + i * step;
    const u = phase(t, at, at + span);
    layers.push({
      index: i,
      u,
      opacity: Math.min(1, u * 1.25),
      offset: (1 - u) * 16,
      current: t >= at && t < at + step + span * 0.5,
    });
  }
  return {
    layers,
    total: phase(t, start, start + (count - 1) * step + span),
    done: t >= start + (count - 1) * step + span,
  };
}

/**
 * Contact shadow.
 *
 * Objects that touch something need a shadow at the contact point or the touch
 * reads as overlap. Cheap, and it is the single strongest cue that an action
 * actually happened.
 */
export function contactShadow(
  stage: { g: CanvasRenderingContext2D },
  x: number,
  y: number,
  amount: number,
  radius = 60,
) {
  if (amount <= 0.002) return;
  const g = stage.g;
  g.save();
  try {
    g.globalAlpha = 0.26 * amount;
    g.fillStyle = "#3b3428";
    g.beginPath();
    g.ellipse(x, y, radius * (0.7 + 0.3 * amount), radius * 0.22, 0, 0, Math.PI * 2);
    g.fill();
  } finally {
    g.restore();
  }
}

/**
 * Place props one after another instead of laying them all out at once.
 *
 * A large share of scenes are "these three objects belong in this room". Drawn
 * that way they read as a still life no matter how long the shot runs. This
 * helper gives the scene a spine: each item flies in, lands, and leaves a
 * contact shadow, so the room assembles itself while the narration talks.
 * The director still owns the artwork and the order.
 */
export function place(
  stage: Stage,
  t: number,
  index: number,
  opts: {
    at: number;
    from?: { x: number; y: number };
    to: { x: number; y: number };
    turn?: number;
    shadow?: number;
    scale?: number;
    delay?: number;
    span?: number;
  },
  draw: () => void,
) {
  const from = opts.from ?? { x: opts.to.x + 420, y: opts.to.y - 150 };
  const delay = opts.delay ?? 0;
  const start = opts.at + delay;
  const span = opts.span ?? 0.9;
  const u = phase(t, start, start + span);
  const turn = opts.turn ?? 0.07;
  const smooth = u * u * (3 - 2 * u);
  stage.group(
    {
      x: from.x + (opts.to.x - from.x) * smooth,
      y: from.y + (opts.to.y - from.y) * smooth - Math.sin(smooth * Math.PI) * 16,
      rotation: turn * (1 - smooth),
      scale: (opts.scale ?? 0.9) + (1 - (opts.scale ?? 0.9)) * smooth,
    },
    draw,
  );
  if (u > 0.001) contactShadow(stage, opts.to.x, opts.to.y + (opts.shadow ?? 0), Math.min(1, u * 1.4), index);
}

/**
 * Swap one object for another on the same spot — the most reusable "change"
 * gesture in a paper collage. Outgoing and incoming overlap so the exchange
 * never reads as a cut.
 */
export function swapInPlace(
  stage: Stage,
  t: number,
  opts: { at: number; span?: number; distance?: number },
  outgoing: () => void,
  incoming: () => void,
) {
  const span = opts.span ?? 1.5;
  const distance = opts.distance ?? 300;
  const out = phase(t, opts.at, opts.at + span * 0.7);
  const inn = phase(t, opts.at + span * 0.35, opts.at + span);
  if (out < 1) stage.group({ x: distance * out, y: distance * 0.18 * out, rotation: 0.22 * out, opacity: 1 - out }, outgoing);
  if (inn > 0) stage.group({ x: -distance * (1 - inn), y: -distance * 0.18 * (1 - inn), rotation: -0.18 * (1 - inn) }, incoming);
}
