import type { Stage } from "./stage";
import type { Point, Pose } from "./types";
// A paper pocket owns its occlusion. Registration comes from the asset, never a disease-specific constant.
export function pocket(
  stage: Stage,
  id: string,
  pose: Pose,
  w: number,
  contents: (mouth: Point) => void,
) {
  stage.group(pose, () => {
    stage.image(id, { x: 0, y: 0, w });
    const im = stage.images[id],
      h = (w * im.height) / im.width;
    contents(stage.anchor(id, w, "mouth"));
    const poly = stage.assets[id].registration?.front;
    const pivot = stage.assets[id].registration?.pivot || {x: .5, y: .5};
    if (!poly) throw Error(`缺少前袋轮廓 ${id}`);
    stage.clip(
      () => {
        const g = stage.g;
        g.beginPath();
        poly.forEach(([x, y], i) => {
          if (i) g.lineTo((x - pivot.x) * w, (y - pivot.y) * h);
          else g.moveTo((x - pivot.x) * w, (y - pivot.y) * h);
        });
        g.closePath();
      },
      { x: -w * pivot.x, y: -h * pivot.y, w, h },
      () => stage.image(id, { x: 0, y: 0, w, lift: 0 }),
    );
  });
}
export function hinge(
  stage: Stage,
  pivot: Point,
  width: number,
  height: number,
  openness: number,
  paint: () => void,
) {
  stage.group(pivot, () => {
    const g = stage.g;
    g.save();
    try {
      g.scale(Math.max(0.025, Math.cos((openness * Math.PI) / 2)), 1);
      paint();
    } finally { g.restore(); }
  });
}
export function clipFastener(stage: Stage, x: number, y: number, angle = -0.1) {
  stage.group({ x, y, rotation: angle }, () => {
    const g = stage.g;
    stage.shadow(1);
    g.strokeStyle = "#8c8069";
    g.lineWidth = 3;
    g.beginPath();
    g.moveTo(-6, 15);
    g.lineTo(-6, -10);
    g.bezierCurveTo(-6, -22, 10, -22, 10, -10);
    g.lineTo(10, 15);
    g.bezierCurveTo(10, 24, -12, 24, -12, 12);
    g.lineTo(-12, -8);
    g.stroke();
  });
}
