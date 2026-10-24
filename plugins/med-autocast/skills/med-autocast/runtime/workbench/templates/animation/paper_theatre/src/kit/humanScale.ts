import type { Asset } from './types';

/** A visible anatomical span sets scale; the pose's enclosing box never does. */
export function humanImageWidth(asset: Asset, width: number, height: number, pixelsPerCm: number): number {
  const meta = asset.human_scale, c = meta?.calibration;
  if (!meta || !c || c.status !== 'calibrated') throw Error(`人物姿态尚未标定 ${asset.asset_id}`);
  if (c.source_size.width !== width || c.source_size.height !== height) throw Error(`人物标定原图尺寸不符 ${asset.asset_id}`);
  const span = Math.hypot((c.to.x - c.from.x) * width, (c.to.y - c.from.y) * height);
  if (![meta.nominal_height_cm, c.span_cm, span, pixelsPerCm].every(v => Number.isFinite(v) && v > 0)) {
    throw Error(`无效人物尺度 ${asset.asset_id}`);
  }
  return width * c.span_cm * pixelsPerCm / span;
}
