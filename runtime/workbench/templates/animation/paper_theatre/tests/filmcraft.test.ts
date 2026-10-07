import { test } from "node:test";
import assert from "node:assert/strict";
import { measurePath, pointAt, trace } from "../src/kit/paths.ts";
import { cameraTrack, settle } from "../src/kit/tracks.ts";

test("pen lifts do not become visible connections or inflate arc length", () => {
  const p = measurePath([{op:"M",x:0,y:0},{op:"L",x:3,y:0},
    {op:"M",x:100,y:0},{op:"L",x:100,y:4}]);
  assert.equal(p.length,7);
  assert.deepEqual(pointAt(p,5/7),{x:100,y:2});
  const calls:unknown[]=[];
  const g:any={beginPath:()=>{},moveTo:(...v:number[])=>calls.push(["M",...v]),
    lineTo:(...v:number[])=>calls.push(["L",...v]),stroke:()=>{}};
  trace(g,p,5/7);
  assert.deepEqual(calls,[["M",0,0],["L",3,0],["M",100,0],["L",100,2]]);
});
test("curved reveals stay bounded and degenerate strokes remain consumable", () => {
  const p=measurePath([{op:"M",x:0,y:0},{op:"Q",cx:0,cy:100,x:100,y:100}]);
  assert.ok(p.length>Math.sqrt(20000)&&p.length<200);
  assert.deepEqual(pointAt(p,-1),{x:0,y:0});
  assert.deepEqual(pointAt(p,2),{x:100,y:100});
  assert.deepEqual(pointAt(measurePath([{op:"M",x:3,y:9},{op:"L",x:3,y:9}]),.5),{x:3,y:9});
});
test("camera samples are order independent and remain continuous off object cadence", () => {
  const sample=cameraTrack([{time:2,value:{x:120,y:210,zoom:1.3}},
    {time:0,value:{x:100,y:200,zoom:1},ease:"linear"}]);
  const a=sample(1.07);sample(5);sample(-2);assert.deepEqual(sample(1.07),a);
  assert.equal(sample(1).x,110);
  assert.notDeepEqual(sample(1),sample(1.03));
  assert.equal(settle(.99,1),0);
  assert.ok(Math.abs(settle(5.05,1))<.00001);
});
