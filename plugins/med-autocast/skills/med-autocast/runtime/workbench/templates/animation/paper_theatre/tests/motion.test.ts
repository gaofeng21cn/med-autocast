import { test } from "node:test";
import assert from "node:assert/strict";
import { stampPose, stow, soundTime, onTwos } from "../src/kit/motion.ts";
test("stamp contact, ink and sound share one cue after retiming", () => {
  const score: any = {
    shots: [{ id: "seal", start: 40, events: { contact: 2.9 } }],
  };
  const sound: any = { shot: "seal", event: "contact", kind: "stamp" };
  const target = { x: 721, y: 445 },
    time = soundTime(score, sound);
  const pose = stampPose(time - 40, 2.9, 3.8, target);
  assert.deepEqual(
    [pose.x, pose.y, pose.height, pose.printed],
    [721, 445, 0, true],
  );
  assert.equal(stampPose(2.89, 2.9, 3.8, target).printed, false);
  score.shots[0].start = 47;
  assert.equal(soundTime(score, sound), 49.9);
  assert.throws(() => soundTime(score, { ...sound, event: "missing" }));
});
test("stow uses local destination independent of prior frame requests", () => {
  const from = { x: -300, y: -170, rotation: -0.1, scale: 1 },
    to = { x: 40, y: 60, rotation: 0.05, scale: 0.7 };
  const sample = () => stow(2.2, 1, 3, from, to);
  const a = sample();
  stow(9, 1, 3, from, to);
  stow(0, 1, 3, from, to);
  assert.deepEqual(a, sample());
  const end = stow(3, 1, 3, from, to);
  assert.ok(Math.abs(end.y - to.y) < 1e-8);
  assert.equal(end.x, to.x);
  assert.equal(end.scale, to.scale);
  assert.equal(onTwos(1.02), 1);
  assert.equal(onTwos(1.07), 1);
});

import {pocket} from '../src/kit/props.ts';
test('pocket front mask follows a non-centred asset pivot',()=>{
 const points:number[][]=[];let rect:any;
 const stage:any={assets:{bag:{registration:{pivot:{x:.2,y:.8},front:[[.2,.4],[.8,.4],[.8,.8]]}}},images:{bag:{width:200,height:100}},group:(_:any,f:()=>void)=>f(),image:()=>{},anchor:()=>({x:60,y:-10}),clip:(f:()=>void,r:any,draw:()=>void)=>{f();rect=r;draw()},g:{beginPath:()=>{},moveTo:(...p:number[])=>points.push(p),lineTo:(...p:number[])=>points.push(p),closePath:()=>{}}};
 pocket(stage,'bag',{x:400,y:300},200,mouth=>assert.deepEqual(mouth,{x:60,y:-10}));
 assert.deepEqual(rect,{x:-40,y:-80,w:200,h:100});
 assert.ok(Math.abs(points[1][0]-120)<1e-8);assert.equal(points[1][1],-40);
});
