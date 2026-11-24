import React from "react";
import { AbsoluteFill, Audio, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Brand, Score } from "../kit/types";
import { SPRING } from "../kit/motion.ts";
import { sampleScoreAtFrame } from "./seekBridge.ts";

export type PaperTheatreCompositionProps = {
  score: Score;
  brand?: Brand;
  audioSrc?: string;
  clean?: boolean;
  styleId?: string;
  width?: number;
  height?: number;
};

export const PaperTheatreComposition: React.FC<PaperTheatreCompositionProps> = ({
  score,
  brand,
  audioSrc,
  clean = false,
  styleId,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sample = sampleScoreAtFrame(score, frame, fps, clean);
  const localFrame = Math.max(0, Math.round(sample.localTime * fps));
  const enter = spring({
    frame: localFrame,
    fps,
    config: { stiffness: SPRING.paper.stiffness, damping: SPRING.paper.damping, mass: 1 },
  });
  const cardY = interpolate(enter, [0, 1], [36, 0]);
  const cardOpacity = interpolate(enter, [0, 0.4], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (typeof window !== "undefined") {
    const win = window as unknown as Record<string, unknown>;
    win.__rendererId = "remotion_dom";
    win.__requestedStyleId = score.style?.styleId;
    win.__styleId = styleId ?? sample.styleId;
    win.__score = score;
    win.__total = score.duration;
    win.__cuts = [...score.shots.map((s) => s.start), score.duration];
    win.__state = {
      scene: sample.scene,
      time: sample.time,
      localTime: sample.localTime,
      shot: sample.shot,
      progress: sample.progress,
      events: sample.beat.events,
      performance: [],
    };
  }

  return (
    <AbsoluteFill
      id="film"
      style={{
        backgroundColor: "#f6efe2",
        fontFamily: "'PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', sans-serif",
        color: "#22343a",
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      {audioSrc ? <Audio src={audioSrc} /> : null}
      <div
        style={{
          width: "72%",
          maxWidth: 900,
          padding: "40px 48px",
          backgroundColor: "#fffaf0",
          borderRadius: 12,
          border: "2px solid #d9ccb4",
          boxShadow: "0 14px 32px rgba(34, 52, 58, 0.12)",
          transform: `translateY(${cardY.toFixed(2)}px)`,
          opacity: cardOpacity,
        }}
      >
        <div style={{ fontSize: 18, letterSpacing: 1.5, color: "#5d736f", marginBottom: 12 }}>
          {sample.shot}
        </div>
        <div style={{ fontSize: 40, fontWeight: 600, lineHeight: 1.35 }}>
          {sample.beat.title}
        </div>
      </div>
      {brand?.text ? (
        <div
          style={{
            position: "absolute",
            top: 20,
            right: 28,
            fontSize: 18,
            fontWeight: 600,
            color: brand.ink || "#214f55",
          }}
        >
          {brand.text}
        </div>
      ) : null}
      {!clean && sample.subtitle ? (
        <div
          style={{
            position: "absolute",
            bottom: 34,
            left: 64,
            right: 64,
            textAlign: "center",
            fontSize: 30,
            fontWeight: 600,
            lineHeight: 1.35,
            color: "#ffffff",
            textShadow: "0 2px 6px rgba(24, 24, 24, 0.9), 0 0 2px #252525",
            whiteSpace: "pre-line",
          }}
        >
          {sample.subtitle}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
