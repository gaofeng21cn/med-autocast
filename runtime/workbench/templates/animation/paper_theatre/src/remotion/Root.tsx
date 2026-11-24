import React from "react";
import { Composition } from "remotion";
import type { Brand, Score } from "../kit/types";
import scoreData from "../../score.json";
import brandData from "../../brand.json";
import {
  PaperTheatreComposition,
  type PaperTheatreCompositionProps,
} from "./PaperTheatreComposition";

const defaultScore = scoreData as unknown as Score;
const rawBrand = brandData as unknown as Brand & { enabled?: boolean };

export const RemotionRoot: React.FC = () => {
  const fps = defaultScore.fps || 24;
  const durationInFrames = Math.max(1, Math.ceil(defaultScore.duration * fps));
  return (
    <Composition
      id="PaperTheatre"
      component={PaperTheatreComposition}
      durationInFrames={durationInFrames}
      fps={fps}
      width={1280}
      height={720}
      defaultProps={
        {
          score: defaultScore,
          brand: rawBrand.enabled ? rawBrand : undefined,
        } satisfies PaperTheatreCompositionProps
      }
      calculateMetadata={({ props }) => {
        const activeScore = props.score || defaultScore;
        const activeFps = activeScore.fps || fps;
        return {
          fps: activeFps,
          durationInFrames: Math.max(1, Math.ceil(activeScore.duration * activeFps)),
          width: props.width || 1280,
          height: props.height || 720,
        };
      }}
    />
  );
};
