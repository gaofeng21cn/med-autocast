import test from "node:test";
import assert from "node:assert/strict";
import type { Stage } from "../src/kit/stage";
import { scene } from "../src/kit/scene.ts";

test("director layer order preserves layout ownership", () => {
  const drawn: [string, boolean][] = [];
  const stage = { tracking: true, group: (_: unknown, draw: () => void) => draw() } as Stage;
  scene(stage, [
    { id: "desk", role: "environment", draw: () => drawn.push(["desk", stage.tracking]) },
    { id: "report", role: "subject", draw: () => drawn.push(["report", stage.tracking]) },
    { id: "pocket", role: "foreground", draw: () => drawn.push(["pocket", stage.tracking]) },
    { id: "trim", role: "foreground", trackLayout: false, draw: () => drawn.push(["trim", stage.tracking]) },
  ]);
  assert.deepEqual(drawn, [["desk", false], ["report", true], ["pocket", true], ["trim", false]]);
  assert.equal(stage.tracking, true);
});

test("nested scenes and exceptions do not leak layout tracking", () => {
  const stage = { tracking: true, group: (_: unknown, draw: () => void) => draw() } as Stage;
  assert.throws(() => scene(stage, [{
    id: "environment", role: "environment", draw: () => {
      scene(stage, [{ id: "detail", role: "subject", draw: () => assert.equal(stage.tracking, false) }]);
      throw Error("failed drawing");
    },
  }]), /failed drawing/);
  assert.equal(stage.tracking, true);
});
