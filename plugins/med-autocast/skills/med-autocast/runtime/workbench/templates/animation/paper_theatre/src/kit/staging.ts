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


/**
 * Backdrop as a pasted paper sheet.
 *
 * A collage fails the moment the backdrop is a photograph or a smooth digital
 * illustration: the frame then reads as a photo with paper stuck on it. No
 * amount of subject craft repairs that, and replacing every stock image is not
 * a sustainable fix either. So the medium is enforced here, at draw time: the
 * plate is pulled toward paper stock, given fibre and blotch, and its border
 * is torn with a soft shadow so it reads as a sheet that was laid down rather
 * than a window onto somewhere else.
 *
 * Drawn before the subject, so cut-paper subjects stay crisp on top.
 * strength dials the treatment back for a deliberately photographic moment;
 * 0 disables it.
 */
export function paperPlate(
  stage: Stage,
  image: HTMLImageElement,
  opts: { strength?: number; seed?: number; torn?: boolean } = {},
) {
  const strength = opts.strength ?? 1;
  const seed = opts.seed ?? 17;
  const w = stage.width,
    h = stage.height;
  const g = stage.g;
  if (strength <= 0.001) {
    g.drawImage(image, 0, 0, w, h);
    return;
  }
  g.save();
  try {
    // 1. the sheet itself: pulled toward paper stock, gently flattened.
    g.filter =
      `saturate(${(0.74 - 0.1 * strength).toFixed(3)}) ` +
      `contrast(${(0.95 - 0.06 * strength).toFixed(3)}) ` +
      `brightness(${(1.02 + 0.03 * strength).toFixed(3)}) ` +
      `sepia(${(0.1 * strength).toFixed(3)})`;
    g.drawImage(image, 0, 0, w, h);
    g.filter = 'none';

    // 2. fibre and blotch, so large flats are never dead.
    g.globalCompositeOperation = 'multiply';
    g.globalAlpha = 0.1 * strength;
    const drift = Math.sin(seed) * 4;
    for (let i = 0; i < 260; i++) {
      const x = (((i * 97.13 + drift) % w) + w) % w;
      const y = (((i * 53.71 + drift * 2) % h) + h) % h;
      const len = 14 + ((i * 31) % 40);
      g.strokeStyle = i % 3 ? '#8b7c5c' : '#fff6e2';
      g.lineWidth = 1;
      g.beginPath();
      g.moveTo(x, y);
      g.lineTo(x + len, y + ((i % 5) - 2) * 2.4);
      g.stroke();
    }
    g.globalCompositeOperation = 'source-over';
    g.globalAlpha = 1;
  } finally {
    g.restore();
  }

  if (opts.torn === false) return;

  // 3. torn border: the plate stops being a viewport and becomes a sheet with
  //    an edge, which is what tells the eye it belongs in the collage.
  const bite = 14;
  g.save();
  try {
    g.globalAlpha = 0.3 * strength;
    g.strokeStyle = '#4a3f2c';
    g.lineWidth = 3;
    g.beginPath();
    let x = 0;
    g.moveTo(0, 0);
    while (x < w) {
      x = Math.min(w, x + 60 + ((x * 13) % 47));
      g.lineTo(x, ((x * 7) % bite) - bite / 2);
    }
    g.lineTo(w, h);
    x = w;
    while (x > 0) {
      x = Math.max(0, x - 60 - ((x * 17) % 47));
      g.lineTo(x, h + (((x * 11) % bite) - bite / 2));
    }
    g.stroke();
    g.globalAlpha = 0.12 * strength;
    g.strokeStyle = '#fff8e8';
    g.lineWidth = 1.4;
    g.stroke();
  } finally {
    g.restore();
  }
}
