import type { Stage } from './stage';
import { cutout, grain, tornEllipse } from './materials';

/**
 * Rooms drawn as collage, not photographed.
 *
 * Stock backdrops arrive as photographs or smooth digital illustration, and a
 * cut-paper subject pasted on either reads as a photo with stickers on it. A
 * room built from torn paper sheets fixes the medium at the source: wall,
 * window, counter and props are all the same material as the actors, so the
 * frame is one collage instead of a set with cut-outs standing in front of it.
 *
 * Two rules keep the room from becoming another empty colour field. Every room
 * has built furniture (a bed, a desk, a bench) that explains what surface the
 * subjects will rest on, and every room has at least one fixed detail (a chart,
 * a shelf, a rail) that gives the eye somewhere to go. The room stays quiet:
 * it is scenery, and it must never compete with what the episode puts in it.
 *
 * This is scenery, not staging. It decides the room; the episode still decides
 * what enters it, from which side, in what order, and what it means.
 */
export type RoomKind = 'consult' | 'kitchen' | 'bedroom' | 'lab' | 'ward' | 'home';

interface RoomSpec {
  wall: string;
  sheet: string;
  band: string;
  bandEdge: string;
  bandTop: number;
  night?: boolean;
  window?: { x: number; y: number; w: number; h: number; pane: string; curtain?: boolean };
  shelf?: { x: number; y: number; w: number; props: 'jars' | 'cards' | 'bottles' | 'none' };
  chart?: { x: number; y: number; w: number; h: number };
  rail?: boolean;
  glow?: { x: number; y: number; r: number };
}

const SPECS: Record<RoomKind, RoomSpec> = {
  home: {
    wall: '#e6dcc8',
    sheet: '#f0e7d3',
    band: '#c6b391',
    bandEdge: '#a8977a',
    bandTop: 468,
    window: { x: 138, y: 172, w: 200, h: 150, pane: '#cbd6d1', curtain: true },
    shelf: { x: 1010, y: 176, w: 176, props: 'cards' },
    chart: { x: 686, y: 200, w: 168, h: 122 },
  },
  consult: {
    wall: '#e7ddca',
    sheet: '#f0e8d6',
    band: '#c9b795',
    bandEdge: '#ae9b78',
    bandTop: 462,
    window: { x: 132, y: 170, w: 208, h: 156, pane: '#c9d4d1', curtain: true },
    shelf: { x: 1024, y: 172, w: 168, props: 'cards' },
    chart: { x: 700, y: 196, w: 178, h: 128 },
  },
  kitchen: {
    wall: '#e2e6da',
    sheet: '#ecefe3',
    band: '#d8c8a6',
    bandEdge: '#bfae8b',
    bandTop: 452,
    window: { x: 198, y: 152, w: 204, h: 146, pane: '#cfdad6', curtain: true },
    shelf: { x: 962, y: 166, w: 188, props: 'jars' },
  },
  bedroom: {
    wall: '#31405a',
    sheet: '#3b4b64',
    band: '#4b5c74',
    bandEdge: '#3a485d',
    bandTop: 470,
    night: true,
    window: { x: 902, y: 140, w: 200, h: 164, pane: '#1c2a3d', curtain: true },
    glow: { x: 236, y: 250, r: 320 },
  },
  lab: {
    wall: '#dee5e1',
    sheet: '#e9efeb',
    band: '#c4cdc8',
    bandEdge: '#a7b2ad',
    bandTop: 462,
    window: { x: 142, y: 166, w: 196, h: 148, pane: '#cbd7d4' },
    shelf: { x: 950, y: 170, w: 198, props: 'bottles' },
    chart: { x: 610, y: 198, w: 164, h: 120 },
  },
  ward: {
    wall: '#e4e8e0',
    sheet: '#eef0e8',
    band: '#cfd8cd',
    bandEdge: '#aebbad',
    bandTop: 478,
    window: { x: 152, y: 174, w: 194, h: 144, pane: '#cbd6d1' },
    rail: true,
    shelf: { x: 1024, y: 198, w: 146, props: 'bottles' },
  },
};

function pane(s: Stage, spec: RoomSpec, w: NonNullable<RoomSpec['window']>, seed: number) {
  s.group({ x: w.x, y: w.y }, () => {
    s.paper({ x: 0, y: 0, w: w.w, h: w.h, color: spec.sheet, seed, lift: 4, name: '窗框纸' });
    s.paper({
      x: 0,
      y: 0,
      w: w.w - 18,
      h: w.h - 18,
      color: w.pane,
      seed: seed + 7,
      lift: 0,
      name: '窗纸'
    });
    const g = s.g;
    g.save();
    g.globalAlpha *= 0.5;
    g.strokeStyle = spec.bandEdge;
    g.lineWidth = 3;
    g.beginPath();
    g.moveTo(-w.w / 2 + 9, 0);
    g.lineTo(w.w / 2 - 9, 0);
    g.moveTo(0, -w.h / 2 + 9);
    g.lineTo(0, w.h / 2 - 9);
    g.stroke();
    g.restore();
    if (spec.night) {
      s.group({ x: w.w * 0.2, y: -w.h * 0.22 }, () =>
        cutout(s, { x: 0, y: 0 }, tornEllipse(14, 14, seed + 3, 1.2), '#f2e8c9', seed + 3, 0),
      );
    }
    if (w.curtain) {
      // Curtains are two narrow torn strips, tied back: they frame the window
      // and give the wall a vertical accent without adding another colour.
      [
        { x: -w.w / 2 - 6, flip: 1 },
        { x: w.w / 2 + 6, flip: -1 },
      ].forEach(({ x, flip }, i) =>
        s.group({ x, y: 4, rotation: 0.02 * flip }, () =>
          s.paper({
            x: 0,
            y: 0,
            w: 34,
            h: w.h + 30,
            color: i ? spec.sheet : spec.wall,
            seed: seed + 40 + i,
            lift: 3,
            name: '窗帘纸'
          }),
        ),
      );
    }
    s.bounds({ x: -w.w / 2 - 24, y: -w.h / 2, w: w.w + 48, h: w.h, name: '窗' });
  });
}

export function paperRoom(s: Stage, kind: RoomKind, opts: { seed?: number } = {}) {
  const spec = SPECS[kind];
  const seed = opts.seed ?? 101;
  const w = s.width;
  const h = s.height;
  const g = s.g;
  const oldTracking = s.tracking;
  s.tracking = false;
  g.save();
  try {
    g.fillStyle = spec.wall;
    g.fillRect(0, 0, w, h);
    const wash = g.createLinearGradient(0, 0, w * 0.72, h);
    wash.addColorStop(0, 'rgba(255,250,236,0.32)');
    wash.addColorStop(1, 'rgba(60,48,32,0.18)');
    g.fillStyle = wash;
    g.fillRect(0, 0, w, h);
    s.paper({
      x: w / 2,
      y: spec.bandTop - 232,
      w: w - 48,
      h: 420,
      color: spec.sheet,
      seed,
      lift: 0,
      name: '墙面纸'
    });
    grain(g, w, spec.bandTop, seed + 2, 0.07, 700);

    if (spec.window) pane(s, spec, spec.window, seed + 11);

    if (spec.chart) {
      // A wall chart is functional scenery: it tells the room what kind of
      // place it is, and it is where a record can be pinned later.
      const c = spec.chart;
      s.group({ x: c.x, y: c.y }, () => {
        s.paper({ x: 0, y: 0, w: c.w, h: c.h, color: '#f6f0e0', seed: seed + 51, lift: 3, name: '墙面图表' });
        const gg = s.g;
        gg.save();
        gg.globalAlpha *= 0.45;
        gg.strokeStyle = spec.bandEdge;
        gg.lineWidth = 2;
        for (let i = 1; i < 4; i++) {
          gg.beginPath();
          gg.moveTo(-c.w * 0.36, -c.h * 0.3 + (i * c.h) / 5);
          gg.lineTo(c.w * 0.36, -c.h * 0.3 + (i * c.h) / 5);
          gg.stroke();
        }
        gg.restore();
      });
    }

    if (spec.shelf && spec.shelf.props !== 'none') {
      const sh = spec.shelf;
      s.group({ x: sh.x, y: sh.y }, () => {
        s.paper({ x: 0, y: 0, w: sh.w, h: 14, color: spec.band, seed: seed + 21, lift: 5, name: '搁板' });
        if (sh.props === 'cards') {
          s.paper({ x: -34, y: -40, w: 54, h: 42, color: '#f5efdd', seed: seed + 22, lift: 2, name: '纸卡' });
          s.paper({ x: 30, y: -32, w: 46, h: 34, color: '#efe6cf', seed: seed + 23, lift: 2, name: '纸卡' });
        } else if (sh.props === 'jars') {
          ['#9fb08d', '#c2a37c', '#a8b6b0'].forEach((color, i) =>
            s.group({ x: -46 + i * 46, y: -32 }, () =>
              cutout(
                s,
                { x: 0, y: 0 },
                [
                  { x: -15, y: -22 },
                  { x: 15, y: -22 },
                  { x: 17, y: 14 },
                  { x: -17, y: 14 },
                ],
                color,
                seed + 24 + i,
                1,
              ),
            ),
          );
        } else {
          ['#8fb0a8', '#c9a97e', '#9aa8bd'].forEach((color, i) =>
            s.group({ x: -52 + i * 52, y: -28 }, () =>
              cutout(
                s,
                { x: 0, y: 0 },
                [
                  { x: -12, y: -30 },
                  { x: 12, y: -30 },
                  { x: 14, y: 12 },
                  { x: -14, y: 12 },
                ],
                color,
                seed + 26 + i,
                1,
              ),
            ),
          );
        }
      });
    }

    // The work surface. Its front edge is what tells the viewer this is a
    // table, not a colour change at the bottom of the wall.
    const bandH = h - spec.bandTop;
    s.group({ x: w / 2, y: spec.bandTop + bandH / 2 }, () => {
      s.paper({ x: 0, y: 0, w, h: bandH + 46, color: spec.band, seed: seed + 31, lift: 6, name: '台面纸' });
      s.paper({ x: 0, y: bandH / 2 - 6, w, h: 18, color: spec.bandEdge, seed: seed + 32, lift: 0, name: '台沿' });
      s.bounds({ x: -w / 2, y: -bandH / 2 - 24, w, h: bandH + 48, name: '工作台' });
    });

    if (kind === 'bedroom' || kind === 'ward') {
      // A bed is a built object: headboard, mattress, blanket with a folded
      // edge, pillow. Without it the lower half of the frame is a flat block.
      const bx = kind === 'bedroom' ? 372 : 640;
      const bw = kind === 'bedroom' ? 560 : 620;
      s.group({ x: bx, y: spec.bandTop + 96 }, () => {
        s.paper({ x: 0, y: -66, w: bw + 44, h: 96, color: spec.bandEdge, seed: seed + 61, lift: 3, name: '床头板' });
        s.paper({ x: 0, y: -8, w: bw, h: 88, color: '#e7e2d4', seed: seed + 62, lift: 4, name: '床垫' });
        s.paper({ x: -bw * 0.03, y: 34, w: bw * 0.92, h: 54, color: kind === 'bedroom' ? '#8fa2b6' : '#b9c9bd', seed: seed + 63, lift: 5, name: '被面纸' });
        s.paper({ x: -bw * 0.03, y: 20, w: bw * 0.92, h: 12, color: '#f4efe2', seed: seed + 64, lift: 6, name: '被沿折边' });
        s.paper({ x: -bw * 0.34, y: -22, w: 108, h: 44, color: '#f6f2e7', seed: seed + 65, lift: 6, name: '枕头纸' });
        s.bounds({ x: -bw / 2 - 30, y: -110, w: bw + 70, h: 220, name: '床' });
      });
    }

    if (spec.rail) {
      g.save();
      g.globalAlpha *= 0.85;
      g.strokeStyle = '#b7bfb3';
      g.lineWidth = 5;
      g.beginPath();
      g.moveTo(w * 0.5, spec.bandTop - 226);
      g.lineTo(w - 26, spec.bandTop - 226);
      g.stroke();
      g.restore();
    }

    if (spec.glow) {
      const gl = g.createRadialGradient(spec.glow.x, spec.glow.y, 8, spec.glow.x, spec.glow.y, spec.glow.r);
      gl.addColorStop(0, 'rgba(255,236,190,0.42)');
      gl.addColorStop(1, 'rgba(255,236,190,0)');
      g.save();
      g.fillStyle = gl;
      g.fillRect(spec.glow.x - spec.glow.r, spec.glow.y - spec.glow.r, spec.glow.r * 2, spec.glow.r * 2);
      g.restore();
    }
  } finally {
    g.restore();
    s.tracking = oldTracking;
  }
}
