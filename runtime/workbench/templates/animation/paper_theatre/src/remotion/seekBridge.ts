import type { Beat, Score } from "../kit/types";
import { clamp } from "../kit/motion.ts";

export type RemotionTimelineSample = {
  frame: number;
  time: number;
  localTime: number;
  scene: number;
  shot: string;
  beat: Beat;
  progress: number;
  styleId: string | undefined;
  subtitle: string | undefined;
};

/**
 * Convert master-clock seconds to deterministic Remotion frame index without
 * introducing a second timeline.
 */
export function secondsToFrame(seconds: number, fps: number, duration: number): number {
  const safeFps = Math.max(1, fps);
  const totalFrames = Math.max(1, Math.ceil(duration * safeFps));
  const clamped = clamp(seconds, 0, Math.max(0, duration - 1e-6));
  return Math.min(totalFrames - 1, Math.max(0, Math.round(clamped * safeFps)));
}

/**
 * Sample the active shot, local beat time, style identity, and subtitle cue
 * purely from a Remotion frame and the master-clock score.
 */
export function sampleScoreAtFrame(
  score: Score,
  frame: number,
  fps = score.fps || 24,
  clean = false,
): RemotionTimelineSample {
  const safeFps = Math.max(1, fps);
  const time = clamp(frame / safeFps, 0, Math.max(0, score.duration - 1e-6));
  const idx = Math.max(
    0,
    score.shots.findIndex((b) => time >= b.start && time < b.end),
  );
  const beat = score.shots[idx];
  const localTime = Math.max(0, time - beat.start);
  const span = Math.max(1e-6, beat.end - beat.start);
  const activeCue = clean
    ? undefined
    : score.cues.find((c) => time >= c.start && time < c.end)?.text;
  return {
    frame,
    time,
    localTime,
    scene: idx + 1,
    shot: beat.id,
    beat,
    progress: clamp(localTime / span),
    styleId: beat.styleId || score.style?.appliedStyleId || score.style?.styleId,
    subtitle: activeCue,
  };
}

/**
 * Publish the shared `time-addressable-html-renderer.v1` window contract for a
 * `remotion_dom` page so preview/review tools can seek any frame out of order.
 */
export function installRemotionSeekBridge(
  targetWindow: Record<string, unknown>,
  score: Score,
  onSeekFrame: (frame: number) => void,
  options: { fps?: number; styleId?: string; clean?: boolean } = {},
): void {
  const fps = options.fps ?? score.fps ?? 24;
  targetWindow.__rendererId = "remotion_dom";
  targetWindow.__requestedStyleId = score.style?.styleId;
  targetWindow.__styleId = options.styleId ?? score.style?.appliedStyleId ?? score.style?.styleId;
  targetWindow.__score = score;
  targetWindow.__total = score.duration;
  targetWindow.__cuts = [...score.shots.map((s) => s.start), score.duration];
  targetWindow.__kitVersion = "1.3.0";
  targetWindow.__seek = (tSeconds: number) => {
    const frame = secondsToFrame(tSeconds, fps, score.duration);
    const sample = sampleScoreAtFrame(score, frame, fps, Boolean(options.clean));
    targetWindow.__styleId = options.styleId ?? sample.styleId;
    targetWindow.__state = {
      scene: sample.scene,
      time: sample.time,
      localTime: sample.localTime,
      shot: sample.shot,
      progress: sample.progress,
      events: sample.beat.events,
      performance: [],
    };
    onSeekFrame(frame);
  };
}
