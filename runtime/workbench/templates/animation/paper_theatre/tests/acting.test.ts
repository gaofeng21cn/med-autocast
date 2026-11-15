import { test } from 'node:test';
import assert from 'node:assert/strict';
import { actingFrame, actingSourceRect, resolveActingCue } from '../src/kit/acting.ts';

const beat = (action = 2) => ({
  id: 'S01', title: 'sample', start: 0, end: 8,
  events: { prepare: 0.5, action, reaction: 4, settle: 6 },
  performance: [
    { actor_id: 'dr_mie', asset_id: 'dr_mie_acting', event: 'start', pose: 'attend' },
    { actor_id: 'dr_mie', asset_id: 'dr_mie_acting', event: 'action', pose: 'review' },
    { actor_id: 'dr_mie', asset_id: 'dr_mie_acting', event: 'reaction', pose: 'indicate' },
  ],
});

test('acting cues resolve from the current named event times and keep their transition state', () => {
  const atAction = resolveActingCue(beat(), 2.08, 'dr_mie');
  assert.equal(atAction?.cue.pose, 'review');
  assert.equal(atAction?.previous?.pose, 'attend');
  assert.ok(Math.abs(atAction!.elapsed - 0.08) < 1e-9);
  assert.equal(atAction?.cueTime, 2);

  const retimed = resolveActingCue(beat(3.25), 3.4, 'dr_mie');
  assert.equal(retimed?.cue.pose, 'review');
  assert.ok(Math.abs(retimed!.elapsed - 0.15) < 1e-9);
  assert.equal(retimed?.cueTime, 3.25);
});

test('acting cues do not restart when the previous pose was reached earlier', () => {
  const atReaction = resolveActingCue(beat(), 4.5, 'dr_mie');
  assert.equal(atReaction?.cue.pose, 'indicate');
  assert.equal(atReaction?.previous?.pose, 'review');
  assert.equal(atReaction?.previousElapsed, 2);
  assert.equal(atReaction?.cueTime, 4);
  assert.equal(atReaction?.nextTime, undefined);
});

test('an actor with a delayed first cue is absent before that cue', () => {
  const b = beat();
  b.performance = b.performance.slice(1);
  assert.equal(resolveActingCue(b, 1, 'dr_mie'), undefined);
  assert.equal(resolveActingCue(b, 2, 'other_actor'), undefined);
});

test('pose cues resolve frame from stage duration and validate a 3x4 atlas crop', () => {
  const profile={actor_id:'dr_mie',asset_id:'acting',composition:'full_scene_cell',grid:{columns:3,rows:4,gutter:3},
    poses:{attend:{frames:[0,1],keys:[0,.22]},read:{frames:[5,6],keys:[0,.65]}},
    destination:{x:0,y:0,w:720,h:720}};
  assert.equal(actingFrame(profile,'attend',0.3),1);
  assert.equal(actingFrame(profile,'read',1.0),6);
  assert.deepEqual(actingSourceRect(profile,1086,1448,10),[365,1089,356,356]);
  assert.throws(()=>actingFrame(profile,'missing',0),/没有有效画格时序/);
  assert.throws(()=>actingSourceRect(profile,1086,1448,12),/越界/);
});

test('missing named events fail at the director-to-renderer boundary', () => {
  const invalid = { ...beat(), performance: [
    { actor_id: 'dr_mie', asset_id: 'dr_mie_acting', event: 'missing', pose: 'listen' },
  ] };
  assert.throws(() => resolveActingCue(invalid, 1, 'dr_mie'), /表演事件不存在/);
  const outside = { ...beat(), performance: [
    { actor_id: 'dr_mie', asset_id: 'dr_mie_acting', event: 'settle', offset: 3, pose: 'attend' },
  ] };
  assert.throws(() => resolveActingCue(outside, 7, 'dr_mie'), /表演提示无效/);
});
