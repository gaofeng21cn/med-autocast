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
export function caption(s: Stage, score: Score, t: number) {
  const c = score.cues.find((c) => t >= c.start && t < c.end);
  if (!c) return;
  const g = s.g;
  g.save();
  g.font = '500 27px "PingFang SC",sans-serif';
  g.textAlign = "center";
  g.textBaseline = "middle";
  const lines = c.text.split(/\r\n|\r|\n/);
  const lineHeight = 33;
  // Keep the last line on the existing caption baseline; extra lines grow
  // upwards inside the authored subtitle area rather than below the frame.
  const firstY = s.height - 67 - (lines.length - 1) * lineHeight;
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
  g.shadowColor = "transparent";
  g.lineJoin = "round";
  g.lineWidth = dark ? 3.6 : 2.3;
  g.strokeStyle = dark ? "#263733" : "rgba(255,249,234,.78)";
  g.fillStyle = dark ? "#fff8e8" : "#253f3b";
  lines.forEach((line, i) => {
    const y = firstY + i * lineHeight;
    g.strokeText(line, s.width / 2, y);
    g.fillText(line, s.width / 2, y);
  });
  const metrics = lines.map(line => g.measureText(line));
  const pad = g.lineWidth / 2;
  const left = Math.max(...metrics.map(m => Math.max(m.width/2, m.actualBoundingBoxLeft))) + pad;
  const right = Math.max(...metrics.map(m => Math.max(m.width/2, m.actualBoundingBoxRight))) + pad;
  const top = Math.min(firstY-17, ...metrics.map((m, i) => firstY+i*lineHeight-m.actualBoundingBoxAscent-pad));
  const bottom = Math.max(s.height-50, ...metrics.map((m, i) => firstY+i*lineHeight+m.actualBoundingBoxDescent+pad));
  const rect = { x: s.width/2-left, y: top,
    w: left+right, h: bottom-top, name: c.text };
  g.restore();
  return rect;
}
