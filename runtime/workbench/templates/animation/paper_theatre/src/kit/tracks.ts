import type { Camera, Point, Pose } from "./types";
import { clamp, mix, smooth } from "./motion.ts";

export type Key<T> = { time: number; value: T; ease?: "linear" | "smooth" | "hold" };
// A track is compiled once; sampling has no frame history and supports reverse seeks.
export function track<T extends Record<string, number>>(keys: readonly Key<T>[]) {
  if (!keys.length) throw Error("轨道需要至少一个关键帧");
  const list = [...keys].sort((a, b) => a.time - b.time);
  return (t: number): T => {
    if (t < list[0].time) return { ...list[0].value };
    let i = 0;
    while (i + 1 < list.length && t >= list[i + 1].time) i++;
    if (i === list.length - 1) return { ...list[i].value };
    const a = list[i], b = list[i + 1];
    const p = clamp((t - a.time) / (b.time - a.time));
    const q = a.ease === "hold" ? 0 : a.ease === "linear" ? p : smooth(p);
    return Object.fromEntries(Object.keys(a.value).map(k =>
      [k, mix(a.value[k], b.value[k], q)])) as T;
  };
}
export const cameraTrack = (keys: readonly Key<Camera>[]) => track(keys);
export const poseTrack = (keys: readonly Key<Required<Pose>>[]) => track(keys);

// A reaction decays after an authored contact; no perpetual decorative wobble.
export function settle(t: number, contact: number, amplitude = 1, decay = 6, hz = 3) {
  const dt = t - contact;
  return dt < 0 ? 0 : amplitude * Math.exp(-decay * dt) * Math.sin(dt * Math.PI * 2 * hz);
}
export function hingeRise(t: number, start: number, end: number, base: Point,
  lean = 0): Pose & { squash: number } {
  const p = smooth(clamp((t - start) / Math.max(1e-6, end - start)));
  return { ...base, rotation: lean * (1 - p), squash: Math.sin(p * Math.PI / 2),
    opacity: p > 0 ? 1 : 0, scale: 1 };
}
export function parallax(camera: Point, depth: number): Point {
  return { x: -camera.x * depth, y: -camera.y * depth };
}
