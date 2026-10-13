import type { Stage } from './stage';

/*
 * Text that lives on a paper.
 *
 * Every headline in this series sits on a torn paper strip or a card, and the
 * text has to agree with that paper. Hand-tuned x offsets cannot do that: the
 * same offset that centres a four-character label pushes a twelve-character
 * label off the left edge of the strip. So the position is derived from the
 * paper box instead, and the type size shrinks to fit as a hard floor — a
 * label can never spill off its paper no matter what string it carries.
 *
 * This is the lower bound that keeps every card legible. The director still
 * owns where the card goes and what the paper says; this only guarantees the
 * type and the paper agree once the card is placed.
 */

const FONT_STACK = '"Kaiti SC","STKaiti",serif';

export interface CardTitleOptions {
  size?: number;
  color?: string;
  weight?: number;
  align?: 'left' | 'center' | 'right';
  y?: number;
  inset?: number;
  minSize?: number;
}

function fitSize(
  g: CanvasRenderingContext2D,
  text: string,
  size: number,
  weight: number,
  maxWidth: number,
  minSize: number,
) {
  let use = size;
  g.save();
  g.font = weight + ' ' + use + 'px ' + FONT_STACK;
  let w = g.measureText(text).width;
  while (w > maxWidth && use > minSize) {
    use -= 1;
    g.font = weight + ' ' + use + 'px ' + FONT_STACK;
    w = g.measureText(text).width;
  }
  g.restore();
  return { size: use, width: w };
}

/*
 * Place a label on a paper of width w and height h, both centred on the
 * current origin. The text is centred in the box (or aligned to an inset) and
 * the font shrinks so it always stays on the paper.
 */
export function cardTitle(s: Stage, w: number, h: number, text: string, opts: CardTitleOptions = {}) {
  const size = opts.size ?? 24;
  const weight = opts.weight ?? 600;
  const align = opts.align ?? 'center';
  const inset = opts.inset ?? Math.max(14, w * 0.06);
  const minSize = opts.minSize ?? Math.max(11, Math.round(size * 0.6));
  const maxWidth = Math.max(24, w - inset * 2);
  const fitted = fitSize(s.g, text, size, weight, maxWidth, minSize);
  const x = align === 'left' ? -w / 2 + inset : align === 'right' ? w / 2 - inset : 0;
  const y = opts.y ?? 0;
  s.text(text, x, y, fitted.size, opts.color ?? '#254a48', { align, weight });
  return { x, y, size: fitted.size, width: fitted.width };
}

/*
 * A small paper tag carrying a short keyword (the repeated "note" card in most
 * episodes). Centred in the tag, sitting slightly below centre so a piece of
 * tape can hold the top-right corner without crowding the word.
 */
export function tagLabel(s: Stage, w: number, h: number, text: string, opts: CardTitleOptions = {}) {
  return cardTitle(s, w, h, text, {
    size: opts.size ?? 20,
    color: opts.color ?? '#33504c',
    align: 'center',
    y: opts.y ?? h * 0.24,
    inset: opts.inset ?? Math.max(12, w * 0.08),
    minSize: opts.minSize,
    weight: opts.weight,
  });
}
