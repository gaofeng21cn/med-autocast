import type { Camera } from "./types";
import { Stage } from "./stage";
import { tornEllipse } from "./materials";

/**
 * Unify the whole frame into one medium.
 *
 * The biggest reason a collage still reads as a slide is that the environment
 * plate is photographic while every subject is drawn paper. This pass lays a
 * paper grain, a warm wash and an edge vignette over the finished frame so the
 * two media share the same surface. It is deliberately subtle: it should pull
 * the plate into the paper world, not repaint it.
 */
export function paperWorld(stage: Stage, t: number, amount = 1) {
  if (amount <= 0.001) return;
  const w = stage.width,
    h = stage.height,
    g = stage.g;
  g.save();
  try {
    g.globalAlpha = 0.13 * amount;
    g.globalCompositeOperation = "multiply";
    const wash = g.createLinearGradient(0, 0, w, h);
    wash.addColorStop(0, "#f6efdd");
    wash.addColorStop(0.55, "#e9dfc6");
    wash.addColorStop(1, "#d8ccae");
    g.fillStyle = wash;
    g.fillRect(0, 0, w, h);
    g.globalCompositeOperation = "overlay";
    g.globalAlpha = 0.10 * amount;
    // A slow fibre drift keeps the surface alive without shaking the picture.
    const drift = Math.sin(t * 0.18) * 6;
    for (let i = 0; i < 220; i++) {
      const x = ((i * 97.13 + drift * 3) % w + w) % w,
        y = ((i * 61.77 + drift) % h + h) % h,
        len = 18 + ((i * 37) % 46);
      g.strokeStyle = i % 3 ? "#8d7f61" : "#fff8e6";
      g.lineWidth = 1;
      g.beginPath();
      g.moveTo(x, y);
      g.lineTo(x + len, y + ((i % 5) - 2) * 2.2);
      g.stroke();
    }
    g.globalCompositeOperation = "source-over";
    g.globalAlpha = 1;
    // Edge vignette pushes the eye to the middle of the stage.
    const vig = g.createRadialGradient(w / 2, h * 0.46, h * 0.28, w / 2, h * 0.5, h * 0.92);
    vig.addColorStop(0, "rgba(58,48,32,0)");
    vig.addColorStop(1, `rgba(58,48,32,${0.24 * amount})`);
    g.fillStyle = vig;
    g.fillRect(0, 0, w, h);
  } finally {
    g.restore();
  }
}

/**
 * Foreground paper plane.
 *
 * A collage that is only one plane deep reads as a slide, not as a paper
 * theatre. This layer is drawn *outside* the shot camera and moved with a
 * slightly different rate, so it sweeps past the subject faster than the
 * background does. That differential is what produces depth in Canvas 2D, and
 * it costs no extra asset: the occluders are torn edges of the same paper
 * stock the scene already uses.
 *
 * `amount` scales the whole layer; 0 disables it without a branch at the call
 * site, which keeps every shot able to opt out with one number.
 */
export function foreground(
  stage: Stage,
  t: number,
  camera: Camera,
  opts: {
    amount?: number;
    /** which edge the paper curls in from: 0 left, 1 right */
    side?: number;
    seed?: number;
    /** extra sweep on top of the camera-derived offset */
    drift?: number;
  } = {},
) {
  const amount = opts.amount ?? 1;
  if (amount <= 0.001) return;
  const side = opts.side ?? 0;
  const seed = opts.seed ?? 61;
  const drift = opts.drift ?? 16;
  const w = stage.width;
  const h = stage.height;
  // Caption baseline sits at height-67 and is centred, so the foreground may
  // never enter the middle band. `inward` below is capped well inside it: a
  // torn edge across a subtitle is worse than no depth at all.
  // The foreground plane tracks the camera, then runs ahead of it. Amplitude is
  // tied to the zoom so a close-up does not tear the frame apart.
  const lead = (camera.zoom - 1) * 90 + drift;
  const sweep = Math.sin(t * 0.32 + seed) * lead * 0.22;
  // Clamp so an aggressive zoom cannot slide the leaf across the subtitle.
  const inward = Math.min(lead * 0.55, w * 0.14);
  const g = stage.g;
  stage.group(
    {
      x: side ? w + 150 - inward + sweep : -150 + inward + sweep,
      y: h * 0.5,
      rotation: (side ? -1 : 1) * 0.014 + Math.sin(t * 0.21 + seed) * 0.006,
      opacity: amount,
    },
    () => {
      // Two overlapping torn leaves read as a stack rather than a border.
      for (let i = 0; i < 2; i++) {
        const lw = i ? 128 : 172;
        const g2 = stage.g;
        g2.save();
        try {
          g2.scale(side ? -1 : 1, 1);
          const poly = tornEllipse(lw * 0.62, h * 0.74, seed + i * 17, 2.4);
          stage.clip(
            () => {
              g2.beginPath();
              poly.forEach((pt, k) =>
                k ? g2.lineTo(pt.x - lw * 0.5, pt.y) : g2.moveTo(pt.x - lw * 0.5, pt.y),
              );
              g2.closePath();
            },
            { x: -lw, y: -h * 0.5, w: lw * 2, h: h },
            () => {
              stage.paper({
                x: 0,
                y: i ? 26 : 0,
                w: lw,
                h: h * 1.2,
                color: i ? "#e6dcc4" : "#d9cfb4",
                seed: seed + i * 31,
                lift: 9 + i * 4,
                name: `foreground-leaf-${i}`,
              });
            },
          );
        } finally {
          g2.restore();
        }
      }
    },
  );
  // A whisper of contact shadow keeps the leaf from looking pasted on.
  g.save();
  try {
    g.globalAlpha = 0.1 * amount;
    const grad = g.createLinearGradient(side ? w : 0, 0, side ? w - 120 : 120, 0);
    grad.addColorStop(0, "#2b2418");
    grad.addColorStop(1, "rgba(43,36,24,0)");
    g.fillStyle = grad;
    g.fillRect(side ? w - 150 : 0, 0, 150, h);
  } finally {
    g.restore();
  }
}

