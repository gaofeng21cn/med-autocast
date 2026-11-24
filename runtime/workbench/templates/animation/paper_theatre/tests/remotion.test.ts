import { test } from "node:test";
import assert from "node:assert/strict";
import {
  installRemotionSeekBridge,
  sampleScoreAtFrame,
  secondsToFrame,
} from "../src/remotion/seekBridge.ts";
import type { Score } from "../src/kit/types.ts";

const fixtureScore: Score = {
  fps: 24,
  duration: 6,
  style: { styleId: "kinetic_type", appliedStyleId: "kinetic_type" },
  shots: [
    { id: "S01", title: "Opening beat", start: 0, end: 2.5, events: { enter: 0.4 } },
    { id: "S02", title: "Mechanism", start: 2.5, end: 6, events: { focus: 1.0 } },
  ],
  cues: [
    { start: 0.2, end: 2.2, text: "先看胰岛素如何工作" },
    { start: 3.0, end: 5.5, text: "餐后散步有助平稳血糖" },
  ],
  sounds: [],
};

test("remotion seek bridge locks seconds to master-clock frames deterministically", () => {
  assert.equal(secondsToFrame(0, 24, 6), 0);
  assert.equal(secondsToFrame(2.5, 24, 6), 60);
  assert.equal(secondsToFrame(99, 24, 6), 143);

  const visited: number[] = [];
  const mockWindow: Record<string, unknown> = {};
  installRemotionSeekBridge(mockWindow, fixtureScore, (frame) => visited.push(frame));

  assert.equal(mockWindow.__rendererId, "remotion_dom");
  assert.equal(mockWindow.__requestedStyleId, "kinetic_type");
  assert.equal(mockWindow.__styleId, "kinetic_type");
  assert.deepEqual(mockWindow.__cuts, [0, 2.5, 6]);

  const seek = mockWindow.__seek as (t: number) => void;
  seek(3.5);
  const stateAt35 = structuredClone(mockWindow.__state);
  seek(0.5);
  seek(3.5);
  assert.deepEqual(mockWindow.__state, stateAt35);
  assert.deepEqual(visited, [84, 12, 84]);
});

test("sampleScoreAtFrame respects clean review mode and shot boundaries", () => {
  const withCaption = sampleScoreAtFrame(fixtureScore, 24, 24, false);
  assert.equal(withCaption.shot, "S01");
  assert.equal(withCaption.subtitle, "先看胰岛素如何工作");

  const cleanMode = sampleScoreAtFrame(fixtureScore, 24, 24, true);
  assert.equal(cleanMode.subtitle, undefined);

  const secondShot = sampleScoreAtFrame(fixtureScore, 72, 24, false);
  assert.equal(secondShot.shot, "S02");
  assert.equal(secondShot.scene, 2);
  assert.equal(secondShot.subtitle, "餐后散步有助平稳血糖");
});
