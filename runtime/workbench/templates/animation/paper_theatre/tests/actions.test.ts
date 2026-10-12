import { test } from "node:test";
import assert from "node:assert/strict";
import {
  clipSnap,
  cutAlong,
  drawOut,
  dropSettle,
  foldPose,
  handmade,
  liftPose,
  pageTurn,
  panWith,
  pushIn,
  pullOut,
  strokeAlong,
  tearPose,
  tiltDrift,
  unfoldPanels,
  unroll,
  wrapBand,
} from "../src/kit/motion.ts";

test("action solvers are pure functions of time (random seek safe)", () => {
  const solvers = [
    () => liftPose(2.2, 0.5, 1.4, 2.6, { x: 10, y: 20 }, { x: 300, y: 90 }),
    () => tearPose(1.3, 0.4, 1.9),
    () => foldPose(1.3, 0.4, 1.9),
    () => pageTurn(1.3, 0.4, 1.9),
    () => drawOut(1.3, 0.4, 1.9, 120),
    () => unroll(1.3, 0.4, 1.9, 240),
    () => wrapBand(1.3, 0.4, 1.9, 2),
    () => cutAlong(1.3, 0.4, 1.1, 1.9),
    () => strokeAlong(1.3, 0.4, 1.9),
    () => clipSnap(1.3, 1.1),
    () => dropSettle(1.3, 0.4, 1.1, { x: 0, y: 0 }, { x: 200, y: 160 }),
    () => unfoldPanels(1.3, 0.4, 1.9, 4),
    () => handmade(1.3, 7),
    () => pushIn(1.3, 0.4, 1.9),
    () => panWith(1.3, 0.4, 1.9, { x: 100, y: 200 }, { x: 600, y: 320 }),
    () => pullOut(1.3, 0.4, 1.9),
    () => tiltDrift(1.3, 0.4, 1.9),
  ];
  for (const solve of solvers) {
    const first = JSON.stringify(solve());
    solve();
    solve();
    assert.equal(JSON.stringify(solve()), first);
  }
});

test("lift rises then lands on the authored destination", () => {
  const from = { x: 100, y: 200 },
    to = { x: 500, y: 260 };
  const peak = liftPose(1.4, 0.5, 1.4, 2.6, from, to, 30);
  assert.ok(peak.y < from.y - 10, "paper must leave the surface at peak");
  assert.equal(peak.lift01.toFixed(3), "1.000");
  const landed = liftPose(2.6, 0.5, 1.4, 2.6, from, to, 30);
  assert.equal(Math.round(landed.x), 500);
  assert.equal(Math.round(landed.y), 260);
  assert.ok(landed.lift01 < 0.01);
});

test("tear separates halves in opposite directions on both axes", () => {
  const v = tearPose(9, 0.5, 2, "v");
  assert.ok(v.left.x < 0 && v.right.x > 0);
  assert.ok(v.left.rotation < 0 && v.right.rotation > 0);
  const h = tearPose(9, 0.5, 2, "h");
  assert.ok(h.left.y < 0 && h.right.y > 0);
  assert.equal(tearPose(0, 0.5, 2).amount, 0);
});

test("page turn lifts a corner and reports a real flip", () => {
  const mid = pageTurn(1.2, 0.5, 2.5);
  assert.ok(mid.corner > 0.5, "corner must lift mid-turn");
  assert.ok(mid.flip < 0 && mid.flip > -1);
  const done = pageTurn(3, 0.5, 2.5);
  assert.equal(done.progress, 1);
});

test("cut shares one sever event and only spreads afterwards", () => {
  const before = cutAlong(0.9, 0.4, 1.4, 2.2);
  assert.equal(before.severed, false);
  assert.equal(before.spread, 0);
  const at = cutAlong(1.4, 0.4, 1.4, 2.2);
  assert.equal(at.severed, true);
  const after = cutAlong(2.2, 0.4, 1.4, 2.2);
  assert.ok(after.spread > 0.9);
});

test("drop lands at the target and rings down instead of drifting", () => {
  const landed = dropSettle(4, 0.4, 1.2, { x: 0, y: 0 }, { x: 420, y: 300 });
  assert.equal(landed.landed, true);
  assert.ok(Math.abs(landed.x - 420) < 1e-6);
  assert.ok(Math.abs(landed.y - 300) < 1e-6);
  const justAfter = dropSettle(1.25, 0.4, 1.2, { x: 0, y: 0 }, { x: 420, y: 300 });
  assert.ok(Math.abs(justAfter.x - 420) > 0.5, "landing must produce a small ring");
});

test("camera helpers compose pan, push and drift with authored targets", () => {
  const pushed = pushIn(9, 0.5, 2, 1, 1.3, { x: 900, y: 240 });
  assert.equal(pushed.x, 900);
  assert.equal(pushed.zoom, 1.3);
  const panned = panWith(9, 0.5, 2, { x: 100, y: 200 }, { x: 700, y: 300 }, 1.1);
  assert.deepEqual([panned.x, panned.y, panned.zoom], [700, 300, 1.1]);
  const drift = tiltDrift(1.25, 0.5, 2, 3);
  assert.ok(drift.rotation !== 0);
});

test("wrap, unroll and unfold reach a complete authored end state", () => {
  assert.equal(wrapBand(9, 0.5, 2, 2).turns, 2);
  assert.equal(unroll(9, 0.5, 2, 300).length, 300);
  assert.deepEqual(unfoldPanels(9, 0.5, 2, 4).open, [1, 1, 1, 1]);
});

