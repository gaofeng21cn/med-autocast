import type { Stage } from "./stage";
import type { Pose, Point } from "./types";
import { grain, tape, tornEllipse } from "./materials";
import {
  clipSnap,
  cutAlong,
  drawOut,
  dropSettle,
  foldPose,
  handmade,
  liftPose,
  pageTurn,
  phase,
  strokeAlong,
  tearPose,
  unfoldPanels,
  unroll,
  wrapBand,
} from "./motion";

// ---------------------------------------------------------------------------
// Drawable paper actions.
//
// Each helper owns one physical behaviour and no story. A director composes
// them per shot. `draw` callbacks receive the solved state so callers can supply
// their own artwork without this module prescribing content.
// ---------------------------------------------------------------------------

export type ActionState<T> = {
  /** true once the action has reached its authored contact/result moment */
  done: boolean;
  /** 0..1 progress for effects that should track the solve */
  amount: number;
  state: T;
};

/** Lift a corner or label off a surface. */
export function liftCorner(
  stage: Stage,
  t: number,
  opts: {
    start: number;
    peak: number;
    end: number;
    from: Pose;
    to: Pose;
    w: number;
    h: number;
    color?: string;
    seed?: number;
    lift?: number;
  },
) {
  const p = liftPose(t, opts.start, opts.peak, opts.end, opts.from, opts.to, opts.lift ?? 26);
  stage.group(p, () => {
    stage.paper({
      x: 0,
      y: 0,
      w: opts.w,
      h: opts.h,
      color: opts.color,
      seed: opts.seed ?? 31,
      lift: p.lift01 * (opts.lift ?? 8) + 1,
      name: "lifted-piece",
    });
  });
  return p;
}

/**
 * Tear a sheet along an authored seam. `drawLeft`/`drawRight` receive the two
 * solved poses in the sheet's local space so the halves keep their artwork.
 */
export function tearSheet(
  stage: Stage,
  t: number,
  opts: {
    start: number;
    end: number;
    axis?: "v" | "h";
    x?: number;
    y?: number;
    w: number;
    h: number;
    color?: string;
    seed?: number;
    drawLeft?: (stage: Stage) => void;
    drawRight?: (stage: Stage) => void;
  },
) {
  const axis = opts.axis ?? "v",
    p = tearPose(t, opts.start, opts.end, axis);
  stage.group({ x: opts.x ?? 0, y: opts.y ?? 0 }, () => {
    stage.group({ ...p.left }, () => {
      stage.paper({ x: -opts.w / 4, y: 0, w: opts.w / 2, h: opts.h, color: opts.color, seed: opts.seed ?? 41, lift: 2 + p.amount * 4, name: "tear-left" });
      opts.drawLeft?.(stage);
    });
    stage.group({ ...p.right }, () => {
      stage.paper({ x: opts.w / 4, y: 0, w: opts.w / 2, h: opts.h, color: opts.color, seed: (opts.seed ?? 41) + 1, lift: 2 + p.amount * 4, name: "tear-right" });
      opts.drawRight?.(stage);
    });
    if (p.amount > 0 && p.amount < 1) {
      // Fibre seam: short fibres along the tear become visible while separating.
      const g = stage.g;
      stage.group({ x: 0, y: 0 }, () => {
        g.save();
        g.globalAlpha *= 0.5 * Math.sin(p.amount * Math.PI);
        g.strokeStyle = "#8d7c62";
        g.lineWidth = 1;
        const n = axis === "v" ? 14 : 18;
        for (let i = 0; i < n; i++) {
          const f = (i / (n - 1) - 0.5) * (axis === "v" ? opts.h : opts.w);
          const j = ((i * 37) % 7) - 3;
          g.beginPath();
          if (axis === "v") {
            g.moveTo(j * p.amount * 2, f);
            g.lineTo(j * p.amount * 2 + 3, f + 2);
          } else {
            g.moveTo(f, j * p.amount * 2);
            g.lineTo(f + 2, j * p.amount * 2 + 3);
          }
          g.stroke();
        }
        g.restore();
      });
    }
  });
  return p;
}

/** Fold a panel shut over its content, drawing the crease and shaded inner face. */
export function foldPanel(
  stage: Stage,
  t: number,
  opts: {
    start: number;
    end: number;
    from?: number;
    to?: number;
    x: number;
    y: number;
    w: number;
    h: number;
    color?: string;
    inner?: string;
    seed?: number;
    contents?: () => void;
  },
) {
  const p = foldPose(t, opts.start, opts.end, opts.from, opts.to);
  stage.group({ x: opts.x, y: opts.y }, () => {
    stage.paper({ x: 0, y: 0, w: opts.w, h: opts.h, color: opts.color, seed: opts.seed ?? 51, name: "fold-base" });
    stage.group({ x: 0, y: 0 }, opts.contents ?? (() => {}));
    // The flap scales horizontally; a crease line and a soft inner shade sell
    // the fold without pretending to be a 3D simulation.
    stage.group({ x: -opts.w / 2, y: 0 }, () => {
      stage.group({ x: opts.w / 2, y: 0 }, () => {
        const g = stage.g;
        g.save();
        g.scale(Math.max(0.02, p.openness), 1);
        try {
        stage.paper({ x: opts.w / 2, y: 0, w: opts.w, h: opts.h, color: opts.color, seed: (opts.seed ?? 51) + 7, lift: 3 + p.crease * 5, name: "fold-flap" });
        } finally {
          g.restore();
        }
      });
    });
    const g = stage.g;
    if (p.openness > 0.02 && p.openness < 0.98) {
      g.save();
      g.globalAlpha *= p.crease * 0.5;
      g.strokeStyle = opts.inner ?? "#6b5b45";
      g.lineWidth = 2;
      g.beginPath();
      g.moveTo(-opts.w / 2, 0);
      g.lineTo(opts.w / 2, 0);
      g.stroke();
      g.restore();
    }
  });
  return p;
}

/** Turn a page over a spine, bending it with a corner lift and a moving shadow. */
export function turnPage(
  stage: Stage,
  t: number,
  opts: {
    start: number;
    end: number;
    x: number;
    y: number;
    w: number;
    h: number;
    color?: string;
    seed?: number;
    face?: (stage: Stage) => void;
  },
) {
  const p = pageTurn(t, opts.start, opts.end);
  stage.group({ x: opts.x, y: opts.y }, () => {
    // Under-page stays put.
    stage.paper({ x: opts.w / 4, y: 0, w: opts.w / 2, h: opts.h, color: "#f3ecdb", seed: (opts.seed ?? 61) + 2, name: "page-under" });
    const g = stage.g;
    stage.group({ x: -opts.w / 4, y: 0 }, () => {
      stage.group({ x: opts.w / 4, y: 0, scale: Math.max(0.02, Math.cos(p.flip * Math.PI * 0.5)) }, () => {
        stage.paper({ x: opts.w / 4, y: 0, w: opts.w / 2, h: opts.h, color: opts.color, seed: opts.seed ?? 61, lift: 2 + p.corner * 9, name: "page-turn" });
        opts.face?.(stage);
      });
      if (p.corner > 0.05) {
        g.save();
        // A soft gradient along the fold reads as a bending sheet. A hard
        // triangle read as a solid wedge pasted over the page.
        const grad = g.createLinearGradient(0, -opts.h / 2, opts.w / 2, opts.h / 2);
        grad.addColorStop(0, `rgba(58,48,37,${0.34 * p.corner})`);
        grad.addColorStop(0.55, `rgba(58,48,37,${0.12 * p.corner})`);
        grad.addColorStop(1, "rgba(58,48,37,0)");
        g.globalAlpha = 1;
        g.fillStyle = grad;
        g.beginPath();
        g.moveTo(0, -opts.h / 2);
        g.quadraticCurveTo(opts.w * 0.28, 0, opts.w / 2, opts.h * 0.1);
        g.lineTo(0, opts.h / 2);
        g.closePath();
        g.fill();
        g.restore();
      }
    });
  });
  return p;
}

/** Draw a strip out of a holder (tube, cup, sleeve) along an axis. */
export function pullStrip(
  stage: Stage,
  t: number,
  opts: {
    start: number;
    end: number;
    x: number;
    y: number;
    distance: number;
    axis?: "x" | "y";
    w: number;
    h: number;
    color?: string;
    seed?: number;
  },
) {
  const p = drawOut(t, opts.start, opts.end, opts.distance, opts.axis);
  stage.group({ x: opts.x, y: opts.y }, () => {
    stage.group(p.pose, () => {
      stage.paper({ x: 0, y: 0, w: opts.w, h: opts.h, color: opts.color, seed: opts.seed ?? 71, lift: 4 + p.exposure * 3, name: "pull-strip" });
    });
  });
  return p;
}

/** Unroll a tape or chart; the caller may draw ticks along `length`. */
export function unrollTape(
  stage: Stage,
  t: number,
  opts: { start: number; end: number; x: number; y: number; length: number; h?: number; color?: string; seed?: number; ticks?: (stage: Stage, length: number) => void },
) {
  const p = unroll(t, opts.start, opts.end, opts.length),
    h = opts.h ?? 22;
  stage.group({ x: opts.x, y: opts.y }, () => {
    if (p.length > 1) {
      stage.paper({ x: p.length / 2, y: 0, w: p.length, h, color: opts.color ?? "#e7dcc0", seed: opts.seed ?? 81, lift: 2, name: "tape" });
      opts.ticks?.(stage, p.length);
    }
    // Rolled head stays at the origin and shrinks as the tape pays out.
    stage.group({ x: 0, y: 0 }, () => {
      stage.group({ x: 0, y: 0, scale: 1 - p.curl * 0.4 }, () => {
        stage.paper({ x: 0, y: 0, w: 34, h: h + 10, color: opts.color ?? "#d9caa8", seed: (opts.seed ?? 81) + 3, lift: 4, name: "tape-roll" });
      });
    });
  });
  return p;
}

/** Wrap a band around the current subject. */
export function wrapAround(
  stage: Stage,
  t: number,
  opts: {
    start: number;
    end: number;
    x: number;
    y: number;
    rx: number;
    ry: number;
    turns?: number;
    color?: string;
    seed?: number;
    drawSubject?: () => void;
  },
) {
  const p = wrapBand(t, opts.start, opts.end, opts.turns ?? 1);
  stage.group({ x: opts.x, y: opts.y }, () => {
    opts.drawSubject?.();
    if (p.wrap01 > 0.01) {
      const g = stage.g,
        steps = Math.max(2, Math.round(p.turns * 8));
      g.save();
      g.globalAlpha *= 0.94;
      g.strokeStyle = opts.color ?? "#d9c8a4";
      g.lineWidth = Math.max(4, opts.ry * 0.16);
      g.lineCap = "round";
      for (let i = 0; i < steps; i++) {
        const f = (i + 1) / steps,
          y = (f - 0.5) * opts.ry * 2;
        const k = Math.sqrt(Math.max(0, 1 - (y / opts.ry) ** 2)),
          wob = Math.sin(p.tension * Math.PI) * 3;
        g.beginPath();
        g.moveTo(-opts.rx * k + wob, y);
        g.quadraticCurveTo(0, y + opts.ry * 0.12, opts.rx * k - wob, y);
        g.stroke();
      }
      g.restore();
    }
  });
  return p;
}

/** Cut along an authored blade path and separate the parts afterwards. */
export function cutOpen(
  stage: Stage,
  t: number,
  opts: {
    start: number;
    severAt: number;
    end: number;
    x: number;
    y: number;
    w: number;
    h: number;
    axis?: "v" | "h";
    drawTop?: (stage: Stage, spread: number) => void;
    drawBottom?: (stage: Stage, spread: number) => void;
    blade?: boolean;
  },
) {
  const p = cutAlong(t, opts.start, opts.severAt, opts.end),
    vertical = (opts.axis ?? "v") === "v";
  stage.group({ x: opts.x, y: opts.y }, () => {
    const g = stage.g;
    const top = { x: 0, y: -opts.h * p.spread * 0.28, rotation: -p.spread * 0.03 },
      bottom = { x: 0, y: opts.h * p.spread * 0.28, rotation: p.spread * 0.035 };
    stage.group(bottom, () => opts.drawBottom?.(stage, p.spread));
    stage.group(top, () => opts.drawTop?.(stage, p.spread));
    // The cut line brightens while the blade travels, then stays as an edge.
    g.save();
    g.globalAlpha *= p.severed ? 0.5 : 0.9 * p.blade;
    g.strokeStyle = p.severed ? "#6f6047" : "#fdf6e6";
    g.lineWidth = 2;
    g.beginPath();
    if (vertical) {
      g.moveTo(0, -opts.h / 2);
      g.lineTo(0, -opts.h / 2 + opts.h * p.progress);
    } else {
      g.moveTo(-opts.w / 2, 0);
      g.lineTo(-opts.w / 2 + opts.w * p.progress, 0);
    }
    g.stroke();
    g.restore();
  });
  return p;
}

/** Trace a hand-drawn stroke; supply a `commands` array from `paths.ts`. */
export function penStroke(
  stage: Stage,
  t: number,
  opts: {
    start: number;
    end: number;
    hold?: number;
    color?: string;
    width?: number;
    path: { length: number; segments: { a: Point; b: Point; start: number; length: number; move: boolean }[] };
  },
) {
  const p = strokeAlong(t, opts.start, opts.end, opts.hold ?? 0);
  const g = stage.g;
  g.save();
  g.strokeStyle = opts.color ?? "#3d4a48";
  g.lineWidth = opts.width ?? 2.4;
  g.lineCap = "round";
  g.lineJoin = "round";
  const d = p.fraction * opts.path.length;
  g.beginPath();
  for (const s of opts.path.segments) {
    if (s.start >= d) break;
    if (s.move) g.moveTo(s.a.x, s.a.y);
    const q = Math.min(1, (d - s.start) / s.length);
    g.lineTo(s.a.x + (s.b.x - s.a.x) * q, s.a.y + (s.b.y - s.a.y) * q);
    if (q < 1) break;
  }
  g.stroke();
  // A small nib marks the drawing front while the stroke is live.
  if (p.drawing) {
    g.fillStyle = opts.color ?? "#3d4a48";
    g.beginPath();
    g.arc(opts.path.segments.at(-1)?.b.x ?? 0, opts.path.segments.at(-1)?.b.y ?? 0, opts.width ?? 2.4, 0, Math.PI * 2);
    g.fill();
  }
  g.restore();
  return p;
}

/** Snap a clip shut with a mechanical recoil. */
export function snapClip(
  stage: Stage,
  t: number,
  opts: { closeAt: number; x: number; y: number; angle?: number; scale?: number; color?: string },
) {
  const p = clipSnap(t, opts.closeAt, 1);
  stage.group({ x: opts.x, y: opts.y, rotation: opts.angle ?? -0.1, scale: opts.scale ?? 1 }, () => {
    const g = stage.g;
    g.save();
    g.strokeStyle = opts.color ?? "#8c8069";
    g.lineWidth = 3;
    g.beginPath();
    g.moveTo(-6, 15);
    g.lineTo(-6, -10);
    g.bezierCurveTo(-6, -22, 10, -22, 10, -10);
    g.lineTo(10, 15);
    g.bezierCurveTo(10, 24, -12, 24, -12, 12);
    g.lineTo(-12, -8);
    g.stroke();
    // Jaw gap is the visible mechanical read.
    g.lineWidth = 2.2;
    g.beginPath();
    g.moveTo(-6, 4 - p.gap * 5);
    g.lineTo(10, 4 - p.gap * 5);
    g.stroke();
    g.restore();
  });
  return p;
}

/** Drop a sheet so it falls, lands and rings down. */
export function dropSheet(
  stage: Stage,
  t: number,
  opts: {
    release: number;
    impact: number;
    from: Pose;
    to: Pose;
    w: number;
    h: number;
    color?: string;
    seed?: number;
    face?: () => void;
  },
) {
  const p = dropSettle(t, opts.release, opts.impact, opts.from, opts.to);
  stage.group(p, () => {
    stage.paper({ x: 0, y: 0, w: opts.w, h: opts.h, color: opts.color, seed: opts.seed ?? 91, lift: 1 + p.height * 14, name: "dropped-sheet" });
    opts.face?.();
  });
  return p;
}

/** Open a folded map or board in staggered leaves. */
export function unfoldMap(
  stage: Stage,
  t: number,
  opts: {
    start: number;
    end: number;
    x: number;
    y: number;
    w: number;
    h: number;
    panels: number;
    color?: string;
    seed?: number;
    label?: (stage: Stage, index: number, open: number) => void;
  },
) {
  const p = unfoldPanels(t, opts.start, opts.end, opts.panels),
    leaf = opts.w / opts.panels;
  stage.group({ x: opts.x, y: opts.y }, () => {
    for (let i = 0; i < opts.panels; i++) {
      const open = p.open[i],
        cx = -opts.w / 2 + leaf * (i + 0.5);
      stage.group({ x: cx, y: 0 }, () => {
        // `open` is 0 when folded shut and 1 when fully unfolded, so the leaf
        // must widen with progress rather than narrow.
        stage.group({ x: 0, y: 0, scale: Math.max(0.04, Math.sin(open * Math.PI * 0.5)) }, () => {
          stage.paper({ x: 0, y: 0, w: leaf, h: opts.h, color: opts.color, seed: (opts.seed ?? 101) + i, lift: 1 + open * 5, name: `map-leaf-${i}` });
          opts.label?.(stage, i, open);
        });
      });
    }
  });
  return p;
}

/** Apply hand-made irregularity to one object, never to a whole layer. */
export function handmadePiece(
  stage: Stage,
  t: number,
  seed: number,
  draw: () => void,
  amplitude = 0.004,
) {
  const h = handmade(t, seed, amplitude);
  stage.group({ x: h.dx, y: h.dy, rotation: h.drot }, draw);
}

// Re-export the small set of materials this module's samples rely on so a shot
// file can import from one place when it composes several actions.
export { grain, tape, tornEllipse, phase };

