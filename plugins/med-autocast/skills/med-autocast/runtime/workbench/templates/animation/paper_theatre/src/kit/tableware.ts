import type { Stage } from './stage';
import { cutout, tornEllipse, grain } from './materials';
import { clipFastener } from './props';

export type FoodKind = 'plate' | 'rice' | 'protein' | 'vegetables' | 'fruit' | 'noodle' | 'sweet';

/*
 * Meals drawn as cut paper.
 *
 * Photographic food cut-outs are the last place a collage betrays itself: a real
 * tomato on a ceramic plate reads as a photo pasted onto paper, and no wash
 * fixes the specular highlight on the glaze. So the tableware and the food are
 * drawn here, from torn paper with printed detail, and they scale with the
 * episode's own sense of portion: a vegetable portion and a meat portion are
 * different sizes because they are different things.
 */
export function paperPlate(s: Stage, x: number, y: number, w: number, seed = 41) {
  s.group({ x, y }, () => {
    s.paper({ x: 0, y: 0, w: w * 0.42, h: w * 0.42, color: '#efe7d6', seed, lift: 5, name: '餐盘纸' });
    cutout(s, { x: 0, y: 0 }, tornEllipse(w * 0.38, w * 0.38, seed + 1, 1.6), '#f7f1e3', seed + 1, 0);
    cutout(
      s,
      { x: 0, y: 0 },
      tornEllipse(w * 0.29, w * 0.29, seed + 2, 1.4),
      '#e7dfcb',
      seed + 2,
      0,
    );
    const g = s.g;
    g.save();
    g.globalAlpha *= 0.5;
    g.strokeStyle = '#9c8f72';
    g.lineWidth = 1.6;
    for (let i = 0; i < 6; i++) {
      const a = (i * Math.PI) / 3;
      g.beginPath();
      g.moveTo(Math.cos(a) * w * 0.32, Math.sin(a) * w * 0.32);
      g.lineTo(Math.cos(a) * w * 0.37, Math.sin(a) * w * 0.37);
      g.stroke();
    }
    g.restore();
    s.bounds({ x: -w * 0.42, y: -w * 0.42, w: w * 0.84, h: w * 0.84, name: '餐盘' });
  });
}

export function paperFood(
  s: Stage,
  kind: FoodKind,
  pose: { x: number; y: number; rotation?: number; scale?: number },
  w: number,
  seed = 61,
) {
  s.group({ x: pose.x, y: pose.y, rotation: pose.rotation ?? 0, scale: pose.scale ?? 1 }, () => {
    const g = s.g;
    if (kind === 'rice') {
      cutout(
        s,
        { x: 0, y: w * 0.06 },
        [{ x: -w * 0.46, y: w * 0.2 },
         { x: -w * 0.3, y: -w * 0.2 },
         { x: 0, y: -w * 0.3 },
         { x: w * 0.32, y: -w * 0.18 },
         { x: w * 0.46, y: w * 0.2 },
         { x: 0, y: w * 0.32 }],
        '#f1e9d6',
        seed,
        3,
      );
      g.save();
      g.globalAlpha *= 0.45;
      g.strokeStyle = '#b9ac8f';
      g.lineWidth = 1.2;
      for (let i = 0; i < 9; i++) {
        g.beginPath();
        g.ellipse(-w * 0.3 + (i % 4) * w * 0.2, -w * 0.1 + Math.floor(i / 4) * w * 0.2, w * 0.05, w * 0.028, 0.3, 0, Math.PI * 2);
        g.stroke();
      }
      g.restore();
    } else if (kind === 'protein') {
      cutout(
        s,
        { x: 0, y: 0 },
        [{ x: -w * 0.44, y: -w * 0.18 },
         { x: w * 0.2, y: -w * 0.26 },
         { x: w * 0.46, y: -w * 0.02 },
         { x: w * 0.34, y: w * 0.26 },
         { x: -w * 0.3, y: w * 0.28 },
         { x: -w * 0.48, y: w * 0.06 }],
        '#d9b48c',
        seed,
        3,
      );
      g.save();
      g.globalAlpha *= 0.4;
      g.strokeStyle = '#9c7550';
      g.lineWidth = 1.4;
      for (let i = 0; i < 3; i++) {
        g.beginPath();
        g.moveTo(-w * 0.3, -w * 0.06 + i * w * 0.14);
        g.lineTo(w * 0.3, -w * 0.02 + i * w * 0.14);
        g.stroke();
      }
      g.restore();
    } else if (kind === 'vegetables') {
      [
        ['#8fa87c', -0.26, 0.08, 1.0],
        ['#a8bd82', 0.04, -0.1, 0.9],
        ['#7f9a70', 0.3, 0.1, 0.8],
      ].forEach(([color, dx, dy, k], i) =>
        s.group({ x: (dx as number) * w, y: (dy as number) * w, rotation: (i - 1) * 0.4 }, () =>
          cutout(
            s,
            { x: 0, y: 0 },
            [{ x: -w * 0.24, y: 0 },
             { x: -w * 0.08, y: -w * 0.22 },
             { x: w * 0.2, y: -w * 0.1 },
             { x: w * 0.24, y: w * 0.12 },
             { x: 0, y: w * 0.24 },
             { x: -w * 0.2, y: w * 0.12 }],
            color as string,
            seed + i,
            2 * (k as number) + 1,
          ),
        ),
      );
    } else if (kind === 'fruit') {
      cutout(s, { x: 0, y: 0 }, tornEllipse(w * 0.26, w * 0.25, seed, 1.2), '#c96f5c', seed, 3);
      cutout(
        s,
        { x: w * 0.08, y: -w * 0.24 },
        [{ x: -w * 0.14, y: 0 },
         { x: w * 0.02, y: -w * 0.1 },
         { x: w * 0.16, y: -w * 0.02 },
         { x: w * 0.02, y: w * 0.04 }],
        '#8fa87c',
        seed + 1,
        1,
      );
      g.save();
      g.globalAlpha *= 0.5;
      g.strokeStyle = '#8d4a3c';
      g.lineWidth = 1.4;
      g.beginPath();
      g.moveTo(0, -w * 0.22);
      g.lineTo(w * 0.02, -w * 0.34);
      g.stroke();
      g.restore();
    } else if (kind === 'noodle') {
      cutout(s, { x: 0, y: 0 }, tornEllipse(w * 0.34, w * 0.2, seed, 1.6), '#e6d3ae', seed, 3);
      g.save();
      g.globalAlpha *= 0.55;
      g.strokeStyle = '#b99a6d';
      g.lineWidth = 1.3;
      for (let i = 0; i < 7; i++) {
        g.beginPath();
        g.moveTo(-w * 0.26 + i * w * 0.08, -w * 0.1 + (i % 3) * w * 0.09);
        g.quadraticCurveTo(-w * 0.1 + i * w * 0.08, w * 0.02, -w * 0.02 + i * w * 0.08, w * 0.1 - (i % 2) * w * 0.06);
        g.stroke();
      }
      g.restore();
    } else {
      cutout(
        s,
        { x: 0, y: 0 },
        [{ x: -w * 0.3, y: w * 0.3 },
         { x: -w * 0.3, y: -w * 0.16 },
         { x: 0, y: -w * 0.3 },
         { x: w * 0.3, y: -w * 0.16 },
         { x: w * 0.3, y: w * 0.3 }],
        '#c98f6a',
        seed,
        3,
      );
      grain(g, w, w * 0.6, seed, 0.1, 60);
    }
  });
}

/** A record sheet: torn page, written line, and a clip that holds it down. */
export function sheet(
  s: Stage,
  x: number,
  y: number,
  w: number,
  title: string,
  r = 0,
  t = 8,
  seed = 71,
) {
  s.group({ x, y, rotation: r }, () => {
    s.paper({ x: 0, y: 0, w, h: w * 0.92, color: '#f8f1df', seed, lift: 3, name: title + '纸' });
    s.text(title, -w * 0.3, -w * 0.3, Math.min(24, w * 0.11), '#3c5754');
    const g = s.g;
    const u = Math.min(1, Math.max(0, (t - 0.4) / 1.7));
    g.save();
    g.strokeStyle = '#61786d';
    g.lineWidth = 2.1;
    for (let row = 0; row < 3; row++) {
      g.beginPath();
      g.moveTo(-w * 0.3, -w * 0.06 + row * w * 0.17);
      g.lineTo(-w * 0.3 + w * 0.62 * u, -w * 0.06 + row * w * 0.17);
      g.stroke();
      g.beginPath();
      g.arc(w * 0.26, -w * 0.06 + row * w * 0.17, 2.2, 0, Math.PI * 2);
      g.fillStyle = '#a67953';
      g.fill();
    }
    g.restore();
    clipFastener(s, w * 0.3, -w * 0.44, 0.07);
  });
}
