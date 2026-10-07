import type { Point } from "./types";
import { clamp, mix } from "./motion.ts";
export type PathCommand =
  | { op: "M"; x: number; y: number }
  | { op: "L"; x: number; y: number }
  | { op: "Q"; cx: number; cy: number; x: number; y: number }
  | { op: "C"; c1x: number; c1y: number; c2x: number; c2y: number; x: number; y: number };
type Segment = { a: Point; b: Point; start: number; length: number; move: boolean };
export type MeasuredPath = { segments: Segment[]; length: number; origin: Point };

// Preserve pen lifts. Length-based reveal never draws a bridge across M commands.
// Curves use bounded subdivision; increase samples for very large close-ups.
export function measurePath(commands: readonly PathCommand[], samples = 48): MeasuredPath {
  let p = { x: 0, y: 0 }, length = 0, lifted = true;
  const segments: Segment[] = [];
  const origin = commands.length ? { x: commands[0].x, y: commands[0].y } : p;
  const append = (b: Point) => {
    const d = Math.hypot(b.x - p.x, b.y - p.y);
    if (d > 1e-9) { segments.push({ a: p, b, start: length, length: d, move: lifted }); length += d; lifted = false; }
    p = b;
  };
  for (const c of commands) {
    if (c.op === "M") { p = { x: c.x, y: c.y }; lifted = true; }
    else if (c.op === "L") append({ x: c.x, y: c.y });
    else {
      const a = p;
      for (let i = 1; i <= Math.max(2, samples); i++) {
        const t = i / Math.max(2, samples), u = 1 - t;
        const coordinate = (axis: "x" | "y") => c.op === "Q"
          ? u*u*a[axis] + 2*u*t*(axis === "x" ? c.cx : c.cy) + t*t*c[axis]
          : u*u*u*a[axis] + 3*u*u*t*(axis === "x" ? c.c1x : c.c1y)
            + 3*u*t*t*(axis === "x" ? c.c2x : c.c2y) + t*t*t*c[axis];
        append({ x: coordinate("x"), y: coordinate("y") });
      }
    }
  }
  return { segments, length, origin };
}
export function pointAt(path: MeasuredPath, fraction: number): Point {
  const d = clamp(fraction) * path.length;
  const s = path.segments.find(s => s.start + s.length >= d) || path.segments.at(-1);
  if (!s) return { ...path.origin };
  const p = clamp((d - s.start) / s.length);
  return { x: mix(s.a.x, s.b.x, p), y: mix(s.a.y, s.b.y, p) };
}
export function trace(g: CanvasRenderingContext2D, path: MeasuredPath, fraction: number) {
  const d = clamp(fraction) * path.length;
  g.beginPath();
  for (const s of path.segments) {
    if (s.start >= d) break;
    if (s.move) g.moveTo(s.a.x, s.a.y);
    const p = Math.min(1, (d - s.start) / s.length);
    g.lineTo(mix(s.a.x, s.b.x, p), mix(s.a.y, s.b.y, p));
    if (p < 1) break;
  }
  g.stroke();
}
