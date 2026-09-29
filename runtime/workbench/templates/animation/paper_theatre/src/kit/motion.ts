import type { Point, Pose, Score, Sound } from "./types";
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
export function soundTime(score: Score, event: Sound): number {
  const shot = score.shots.find((s) => s.id === event.shot);
  if (!shot || shot.events[event.event] === undefined)
    throw Error(`声音引用未知事件 ${event.shot}.${event.event}`);
  return shot.start + shot.events[event.event] + (event.offset || 0);
}
