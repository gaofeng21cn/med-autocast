import type { Stage } from "./stage";
export type Point = { x: number; y: number };
export type Rect = Point & { w: number; h: number; name?: string };
export type Pose = Point & {
  scale?: number;
  rotation?: number;
  opacity?: number;
};
export type Camera = Point & { zoom: number; rotation?: number };
export type Asset = {
  asset_id: string;
  path: string;
  registration?: {
    pivot?: Point;
    anchors?: Record<string, Point>;
    front?: number[][];
  };
  human_scale?: {
    nominal_height_cm: number;
    scale_family?: string;
    pose?: string;
    measurement?: string;
    subject?: string;
    calibration?: {
      status: 'calibrated' | 'pending';
      source_sha256: string;
      source_size: { width: number; height: number };
      from: Point;
      to: Point;
      span_cm: number;
      basis: string;
    };
  };
};
export type Beat = {
  id: string;
  title: string;
  start: number;
  end: number;
  events: Record<string, number>;
  performance?: ActingCue[];
  styleId?: string;
};
export type ActingCue = {
  actor_id: string;
  asset_id: string;
  event: string;
  offset?: number;
  pose: string;
};
export type ActingState = {
  actor_id: string;
  asset_id: string;
  event: string;
  pose: string;
  previous_pose?: string;
  transition: number;
  elapsed: number;
  previous_elapsed?: number;
  frame?: number;
  previous_frame?: number;
  source_rect?: [number, number, number, number];
  composition?: 'transparent_pose' | 'full_scene_cell';
};
export type ActingProfile = {
  actor_id: string;
  asset_id: string;
  composition: 'transparent_pose' | 'full_scene_cell';
  grid: { columns: number; rows: number; gutter?: number };
  poses: Record<string, { frames: number[]; keys: number[] }>;
  destination: { x: number; y: number; w: number; h: number };
};
export type Sound = {
  shot: string;
  event: string;
  kind: string;
  asset_id?: string;
  gain?: number;
  offset?: number;
};
export type Score = {
  fps: number;
  duration: number;
  shots: Beat[];
  cues: { start: number; end: number; text: string }[];
  sounds: Sound[];
  style?: AnimationStyleSelection;
};
export type AnimationStyleSelection = {
  styleId?: string;
  appliedStyleId?: string;
  renderer?: string;
  styleProfileRef?: string;
};
export type ShotContext = {
  stage: Stage;
  t: number;
  globalTime: number;
  beat: Beat;
  performanceStates: ActingState[];
  actingProfiles: Record<string, ActingProfile>;
  clean: boolean;
};
export type Shot = {
  id: string;
  render: (ctx: ShotContext) => void;
  camera?: (ctx: ShotContext) => Camera;
  /**
   * Foreground depth. `theatre` sweeps a torn paper leaf in front of the
   * subject; `flat` keeps the legacy single-plane framing; a number scales it.
   */
  depth?: "theatre" | "flat" | number;
};
export type Brand = {
  text: string;
  ink: string;
  accent: string;
  paper: string;
};
export type Layout = { subjects: Rect[]; text: Rect[]; subtitle?: Rect };
declare global {
  interface Window {
    __ready: Promise<void>;
    __seek: (t: number) => void;
    __total: number;
    __cuts: number[];
    __state: {
      scene: number;
      time: number;
      localTime: number;
      shot: string;
      progress: number;
      events: Record<string, number>;
      performance: ActingState[];
    };
    __layout: Layout;
    __score: Score;
    __kitVersion: string;
    __rendererId?: string;
    __styleId?: string;
    __requestedStyleId?: string;
  }
}
