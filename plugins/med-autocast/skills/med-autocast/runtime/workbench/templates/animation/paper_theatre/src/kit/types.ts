import type { Stage } from "./stage";
export type Point = { x: number; y: number };
export type Rect = Point & { w: number; h: number; name?: string };
export type Pose = Point & {
  scale?: number;
  rotation?: number;
  opacity?: number;
};
export type Camera = Point & { zoom: number };
export type Asset = {
  asset_id: string;
  path: string;
  registration?: {
    pivot?: Point;
    anchors?: Record<string, Point>;
    front?: number[][];
  };
};
export type Beat = {
  id: string;
  title: string;
  start: number;
  end: number;
  events: Record<string, number>;
};
export type Sound = {
  shot: string;
  event: string;
  kind: "fold" | "slide" | "stamp";
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
  clean: boolean;
};
export type Shot = {
  id: string;
  render: (ctx: ShotContext) => void;
  camera?: (ctx: ShotContext) => Camera;
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
    };
    __layout: Layout;
    __score: Score;
    __kitVersion: string;
    __rendererId?: string;
    __styleId?: string;
    __requestedStyleId?: string;
  }
}
