import type { Stage } from "./stage";
import type { Brand, Score } from "./types";
export function brandMark(s: Stage, brand: Brand) {
  s.group({ x: 69, y: 44, rotation: -0.035 }, () => {
    s.paper({
      x: 0,
      y: 0,
      w: 97,
      h: 40,
      color: brand.paper,
      seed: 99,
      name: "brand",
    });
    s.text(brand.text, 0, -1, 21, brand.ink);
    const g = s.g;
    g.strokeStyle = brand.accent;
    g.lineWidth = 2;
    g.beginPath();
    g.moveTo(-29, 13);
    g.lineTo(25, 12);
    g.stroke();
  });
}
export function imprint(s: Stage, brand: Brand, x: number, y: number) {
  s.group({ x, y, rotation: -0.1 }, () => {
    const g = s.g;
    g.strokeStyle = brand.paper;
    g.lineWidth = 2.2;
    g.beginPath();
    g.ellipse(0, 0, 47, 26, 0, 0, Math.PI * 2);
    g.stroke();
    s.text(brand.text, 0, -1, 20, brand.paper);
  });
}
function pickBalancedSplit(
  g: CanvasRenderingContext2D,
  chars: string[],
  maxW: number,
  requirePunct: boolean,
): string[] | null {
  const punct = /^[。？！；，、：,.!?;:]$/;
  let bestSplit = -1;
  let bestDiff = Infinity;
  for (let i = 1; i < chars.length; i++) {
    if (requirePunct && !punct.test(chars[i - 1])) continue;
    if (!requirePunct && punct.test(chars[i])) continue;
    const left = chars.slice(0, i).join("");
    const right = chars.slice(i).join("");
    if (!right) continue;
    const lw = g.measureText(left).width;
    const rw = g.measureText(right).width;
    if (lw <= maxW && rw <= maxW) {
      const diff = Math.abs(lw - rw);
      if (diff < bestDiff) {
        bestDiff = diff;
        bestSplit = i;
      }
    }
  }
  return bestSplit > 0 ? [chars.slice(0, bestSplit).join(""), chars.slice(bestSplit).join("")] : null;
}

function wrapCaptionLine(
  g: CanvasRenderingContext2D,
  raw: string,
  targetW: number,
  hardMaxW: number,
): string[] {
  if (!raw || g.measureText(raw).width <= targetW) return [raw];
  const chars = Array.from(raw);
  const byPunctTarget = pickBalancedSplit(g, chars, targetW, true);
  if (byPunctTarget) return byPunctTarget;
  const byPunctHard = pickBalancedSplit(g, chars, hardMaxW, true);
  if (byPunctHard) return byPunctHard;
  const byMidHard = pickBalancedSplit(g, chars, hardMaxW, false);
  if (byMidHard) return byMidHard;
  const punct = /^[。？！；，、：,.!?;:]$/;
  const out: string[] = [];
  let cur = "";
  for (const ch of chars) {
    const cand = cur + ch;
    if (cur && g.measureText(cand).width > hardMaxW && !punct.test(ch)) {
      out.push(cur);
      cur = ch;
    } else {
      cur = cand;
    }
  }
  if (cur) out.push(cur);
  return out;
}

export function caption(s: Stage, score: Score, t: number) {
  const c = score.cues.find((c) => t >= c.start && t < c.end);
  if (!c) return;
  const g = s.g;
  g.save();
  g.font = '600 34px "PingFang SC",sans-serif';
  g.textAlign = "center";
  g.textBaseline = "middle";
  const hardMaxW = Math.max(480, s.width - 120);
  const targetW = Math.min(hardMaxW, 760);
  const lines = c.text
    .split(/\r\n|\r|\n/)
    .flatMap((raw) => wrapCaptionLine(g, raw, targetW, hardMaxW));
  const lineHeight = 48;
  // Keep the last line on the authored caption baseline; extra lines grow
  // upwards cleanly within the safe bottom band without intruding on FLOOR=562.
  const firstY = s.height - 58 - (lines.length - 1) * lineHeight;
  // A textured dark paper floor needs a light caption. Sample its current
  // rendered pixels deterministically instead of adding an opaque color band.
  let luminance = 200;
  try {
    const samples = lines.flatMap((_, i) =>
      [0.25, 0.375, 0.5, 0.625, 0.75].map(x => {
        const d = g.getImageData(Math.round(s.width*x), firstY+i*lineHeight, 1, 1).data;
        return d[0]*.2126 + d[1]*.7152 + d[2]*.0722;
      }));
    luminance = samples.reduce((a,b) => a+b,0)/samples.length;
  } catch { /* Local rendering normally permits pixel reads. */ }
  const dark = luminance < 142;
  g.lineJoin = "round";
  g.lineWidth = 5.6;
  g.strokeStyle = dark ? "rgba(15,30,27,.96)" : "rgba(252,247,235,.98)";
  g.fillStyle = dark ? "#fffdf5" : "#0e221f";
  g.shadowColor = dark ? "rgba(0,0,0,.38)" : "rgba(255,250,238,.85)";
  g.shadowBlur = 3;
  lines.forEach((line, i) => {
    const y = firstY + i * lineHeight;
    g.strokeText(line, s.width / 2, y);
    g.fillText(line, s.width / 2, y);
  });
  g.shadowColor = "transparent";
  g.shadowBlur = 0;
  const metrics = lines.map(line => g.measureText(line));
  const blurPad = 6;
  const pad = g.lineWidth / 2 + blurPad;
  const left = Math.max(...metrics.map(m => Math.max(m.width/2, m.actualBoundingBoxLeft))) + pad;
  const right = Math.max(...metrics.map(m => Math.max(m.width/2, m.actualBoundingBoxRight))) + pad;
  const top = Math.min(firstY-20, ...metrics.map((m, i) => firstY+i*lineHeight-m.actualBoundingBoxAscent-pad));
  const bottom = Math.max(s.height-42, ...metrics.map((m, i) => firstY+i*lineHeight+m.actualBoundingBoxDescent+pad));
  const rect = { x: s.width/2-left, y: top,
    w: left+right, h: bottom-top, name: c.text };
  g.restore();
  return rect;
}
