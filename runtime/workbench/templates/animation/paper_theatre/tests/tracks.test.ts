import test from "node:test";
import assert from "node:assert/strict";
import { track } from "../src/kit/tracks.ts";

test("short movement and a held result survive reverse/random seeks",()=>{
  const sample=track([
    {time:0,value:{x:0}}, {time:2,value:{x:0},ease:"out"},
    {time:2.2,value:{x:100}}, {time:4,value:{x:100},ease:"in"},
    {time:5,value:{x:0}}
  ]);
  assert.equal(sample(1.9).x,0);
  assert.ok(Math.abs(sample(2.1).x-87.5)<1e-9);
  assert.equal(sample(3.7).x,100);
  assert.equal(sample(4.5).x,87.5);
  assert.ok(Math.abs(sample(2.1).x-87.5)<1e-9);
  assert.equal(sample(9).x,0);
});

test("track spring ease is deterministic and settles near target", () => {
  const sample = track([
    { time: 0, value: { x: 0 }, ease: "spring" },
    { time: 1.5, value: { x: 100 } },
  ]);
  const a = sample(0.25).x;
  sample(2.0);
  const b = sample(0.25).x;
  assert.equal(a, b);
  assert.ok(a > 60);
  assert.equal(sample(1.5).x, 100);
});
