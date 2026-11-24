import React from 'react';
import { Composition, registerRoot } from 'remotion';
import { SeekHostComposition, type SeekHostProps } from './SeekHostComposition';

const SeekHostRoot: React.FC = () => {
  return (
    <Composition
      id="SeekHost"
      component={SeekHostComposition}
      durationInFrames={24}
      fps={24}
      width={1280}
      height={720}
      defaultProps={
        {
          entry: 'index.html',
          width: 1280,
          height: 720,
          fps: 24,
          durationInFrames: 24,
        } satisfies SeekHostProps
      }
      calculateMetadata={({ props }) => ({
        fps: props.fps,
        width: props.width,
        height: props.height,
        durationInFrames: props.durationInFrames,
      })}
    />
  );
};

registerRoot(SeekHostRoot);
