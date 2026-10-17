import type { Stage } from './stage';
import type { Rect } from './types';

const FONT_STACK = '"Kaiti SC","STKaiti",serif';
export interface CardTitleOptions {
  size?: number; color?: string; weight?: number;
  align?: 'left' | 'center' | 'right'; y?: number; inset?: number;
  minSize?: number; maxLines?: number; owner?: string;
  placement?: 'on-paper' | 'annotation';
}
export type TextRegion = Rect & { name?: string };
type RegionRecord = {
  text: string; owner?: string; placement: string; region: Rect; ink: Rect;
  local_region: Rect; local_ink: Rect; fits: boolean; size: number;
  lines: string[]; overflow: { left: number; right: number; top: number; bottom: number };
};

function metrics(g: CanvasRenderingContext2D, text: string, size: number, weight: number) {
  g.font = `${weight} ${size}px ${FONT_STACK}`;
  g.textAlign = 'left'; g.textBaseline = 'middle';
  const m = g.measureText(text);
  return {
    left: m.actualBoundingBoxLeft ?? 0,
    right: m.actualBoundingBoxRight ?? m.width,
    ascent: m.actualBoundingBoxAscent ?? size * .62,
    descent: m.actualBoundingBoxDescent ?? size * .62,
    advance: m.width,
  };
}
function wrap(g: CanvasRenderingContext2D, text: string, width: number, size: number, weight: number) {
  const lines: string[] = [];
  for (const paragraph of text.split(/\r\n|\r|\n/)) {
    let line = '';
    for (const character of Array.from(paragraph)) {
      const candidate = line + character, m = metrics(g, candidate, size, weight);
      if (line && Math.max(m.advance, m.left + m.right) > width) {
        lines.push(line); line = character;
      } else line = candidate;
    }
    lines.push(line);
  }
  return lines;
}

/** Explicit local text region. Never guesses a paper owner, truncates or clips.
 * Unfittable text remains visible and is recorded for the director to re-layout.
 */
export function textBox(s: Stage, box: Rect, text: string, opts: CardTitleOptions = {}) {
  const g = s.g, requested = opts.size ?? 24, weight = opts.weight ?? 600;
  const minimum = Math.min(requested, opts.minSize ?? Math.max(14, requested * .75));
  const maxLines = opts.maxLines ?? 2, padding = opts.inset ?? 0;
  const region = { ...box, x: box.x + padding, y: box.y + padding,
    w: Math.max(0, box.w - padding * 2), h: Math.max(0, box.h - padding * 2) };
  const align = opts.align ?? 'center';
  g.save();
  try {
    let chosen: {size: number; lines: string[]; measures: ReturnType<typeof metrics>[]; height: number} | undefined;
    // A short title stays on one line; longer copy may wrap within the same
    // explicit region. The readable minimum is real, never an overflow promise.
    for (const lineLimit of [1, maxLines]) {
      for (let size = requested; ; size = Math.max(minimum, size - 1)) {
        const lines = lineLimit === 1 ? text.split(/\r\n|\r|\n/) : wrap(g, text, region.w, size, weight);
        const measures = lines.map(line => metrics(g, line, size, weight));
        const height = (lines.length - 1) * size * 1.25 + measures[0].ascent + measures.at(-1)!.descent;
        const fits = lines.length <= lineLimit && height <= region.h &&
          measures.every(m => Math.max(m.advance, m.left + m.right) <= region.w);
        if (fits) { chosen = {size, lines, measures, height}; break; }
        if (size === minimum) break;
      }
      if (chosen) break;
    }
    if (!chosen) {
      const lines = wrap(g, text, Math.max(1, region.w), minimum, weight);
      const measures = lines.map(line => metrics(g, line, minimum, weight));
      chosen = {size: minimum, lines, measures,
        height: (lines.length - 1) * minimum * 1.25 + measures[0].ascent + measures.at(-1)!.descent};
    }
    const {size, lines, measures, height} = chosen;
    const firstBaseline = region.y + (region.h - height) / 2 + measures[0].ascent;
    const inkRects: Rect[] = [];
    for (let i = 0; i < lines.length; i++) {
      const m = measures[i], inkWidth = m.left + m.right;
      const left = align === 'left' ? region.x : align === 'right'
        ? region.x + region.w - inkWidth : region.x + (region.w - inkWidth) / 2;
      const baseline = firstBaseline + i * size * 1.25;
      s.text(lines[i], left + m.left, baseline, size, opts.color ?? '#254a48', {align: 'left', weight});
      inkRects.push({x: left, y: baseline - m.ascent, w: inkWidth, h: m.ascent + m.descent});
    }
    const left = Math.min(...inkRects.map(r => r.x)), top = Math.min(...inkRects.map(r => r.y));
    const ink = {x: left, y: top,
      w: Math.max(...inkRects.map(r => r.x + r.w)) - left,
      h: Math.max(...inkRects.map(r => r.y + r.h)) - top, name: text};
    const overflow = {left: Math.max(0, region.x - ink.x), right: Math.max(0, ink.x + ink.w - region.x - region.w),
      top: Math.max(0, region.y - ink.y), bottom: Math.max(0, ink.y + ink.h - region.y - region.h)};
    const fits = Object.values(overflow).every(v => v < .01) && lines.length <= maxLines;
    if (s.tracking && g.globalAlpha >= .025) {
      const layout = s.layout() as ReturnType<Stage['layout']> & {textRegions?: RegionRecord[]};
      (layout.textRegions ??= []).push({text, owner: opts.owner, placement: opts.placement ?? 'on-paper',
        region: {...s.worldRect(region), name: box.name}, ink: {...s.worldRect(ink), name: text},
        local_region: region, local_ink: ink, fits, size, lines, overflow});
    }
    return {x: region.x + region.w / 2, y: region.y + region.h / 2,
      size, width: ink.w, height: ink.h, lines, fits};
  } finally { g.restore(); }
}

export function cardTitle(s: Stage, w: number, h: number, text: string, opts: CardTitleOptions = {}) {
  const inset = opts.inset ?? Math.max(14, w * .06), y = opts.y ?? 0;
  // The safe box is in the very same local coordinates as the paper. A title
  // near an edge gets only the remaining height, not the whole paper height.
  // A narrow badge needs horizontal padding, not that same amount removed
  // vertically. Explicit inset still applies to both axes when requested.
  const verticalInset = opts.inset ?? Math.max(3, Math.min(inset, h * .08));
  const halfHeight = Math.max(0, h / 2 - verticalInset - Math.abs(y));
  return textBox(s, {x: -w / 2 + inset, y: y - halfHeight, w: Math.max(0, w - 2 * inset),
    h: 2 * halfHeight, name: opts.owner ?? '纸上标题排版区'}, text, {...opts, inset: 0, placement: 'on-paper'});
}
export function tagLabel(s: Stage, w: number, h: number, text: string, opts: CardTitleOptions = {}) {
  return cardTitle(s, w, h, text, {...opts, size: opts.size ?? 20, color: opts.color ?? '#33504c',
    align: 'center', y: opts.y ?? (h >= 70 ? h * .24 : 0),
    ...(opts.inset === undefined ? {} : {inset:opts.inset})});
}
