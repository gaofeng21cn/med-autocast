import { test } from 'node:test';
import assert from 'node:assert/strict';
import { humanImageWidth } from '../src/kit/humanScale.ts';

const make = (height: number, from: {x:number;y:number}, to: {x:number;y:number}, span: number) => ({
  asset_id: 'sample', path: 'sample.png',
  human_scale: {nominal_height_cm: height, calibration: {status: 'calibrated' as const,
    source_sha256: 'test', source_size: {width: 1000, height: 1000}, from, to,
    span_cm: span, basis: 'authored reference span'}},
});

test('standing and supine full-body spans share scale without equalizing bounding heights', () => {
  const standing = make(165, {x:.5,y:.05}, {x:.5,y:.95}, 165);
  const lying = make(175, {x:.05,y:.5}, {x:.95,y:.5}, 175);
  assert.ok(Math.abs(humanImageWidth(standing, 1000, 1000, 3) * .9 - 495) < 1e-9);
  assert.ok(Math.abs(humanImageWidth(lying, 1000, 1000, 3) * .9 - 525) < 1e-9);
});

test('seated pose uses the same body segment as its master, not its visible height', () => {
  const standing = make(165, {x:.5,y:.1}, {x:.5,y:.22}, 22);
  const seated = make(165, {x:.4,y:.15}, {x:.4,y:.27}, 22);
  assert.ok(Math.abs(humanImageWidth(standing, 1000, 1000, 3) - humanImageWidth(seated, 1000, 1000, 3)) < 1e-9);
  assert.throws(() => humanImageWidth(seated, 500, 1000, 3), /原图尺寸不符/);
  assert.throws(() => humanImageWidth(seated, 1000, 1000, -3), /无效人物尺度/);
  assert.throws(() => humanImageWidth({asset_id:'unmeasured',path:'x'}, 1000, 1000, 3), /尚未标定/);
});
