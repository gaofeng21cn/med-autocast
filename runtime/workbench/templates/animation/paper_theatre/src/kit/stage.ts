import type { Asset, Camera, Layout, Point, Pose, Rect } from "./types";
import { hash } from "./motion";
export class Stage {
  readonly images: Record<string, HTMLImageElement> = {};
  readonly assets: Record<string, Asset> = {};
  private extents: Record<string, Rect> = {};
  private layoutData: Layout = { subjects: [], text: [] };
  private clips: Rect[] = [];
  tracking = true;
  constructor(
    readonly g: CanvasRenderingContext2D,
    readonly width = 1280,
    readonly height = 720,
  ) {}
  async load(list: Asset[]) {
    await Promise.all(
      list.map(
        (a) =>
          new Promise<void>((resolve, reject) => {
            const im = new Image();
            this.assets[a.asset_id] = a;
            im.onload = () => {
              this.images[a.asset_id] = im;
              const c = document.createElement("canvas");
              c.width = 180;
              c.height = Math.max(1, Math.round((180 * im.height) / im.width));
              const x = c.getContext("2d", { willReadFrequently: true })!;
              x.drawImage(im, 0, 0, c.width, c.height);
              let ext = { x: 0, y: 0, w: 1, h: 1 };
              try {
                const data = x.getImageData(0, 0, c.width, c.height).data;
                let l = c.width,
                  r = 0,
                  t = c.height,
                  b = 0;
                for (let y = 0; y < c.height; y++)
                  for (let i = 0; i < c.width; i++)
                    if (data[(y * c.width + i) * 4 + 3] > 24) {
                      l = Math.min(l, i);
                      r = Math.max(r, i + 1);
                      t = Math.min(t, y);
                      b = Math.max(b, y + 1);
                    }
                if (r > l)
                  ext = {
                    x: l / c.width,
                    y: t / c.height,
                    w: (r - l) / c.width,
                    h: (b - t) / c.height,
                  };
              } catch (e) {
                if (
                  !(e instanceof DOMException) ||
                  e.name !== "SecurityError"
                ) {
                  reject(e);
                  return;
                }
              }
              this.extents[a.asset_id] = ext;
              resolve();
            };
            im.onerror = () => reject(Error(`素材无法加载 ${a.path}`));
            im.src = a.path;
          }),
      ),
    );
  }
  reset() {
    this.g.setTransform(1, 0, 0, 1, 0, 0);
    this.g.globalAlpha = 1;
    this.layoutData = { subjects: [], text: [] };
    this.clips = [];
    this.tracking = true;
  }
  layout() {
    return this.layoutData;
  }
  group(pose: Pose, draw: () => void) {
    const g = this.g;
    g.save();
    try {
      g.translate(pose.x, pose.y);
      g.rotate(pose.rotation || 0);
      g.scale(pose.scale ?? 1, pose.scale ?? 1);
      g.globalAlpha *= pose.opacity ?? 1;
      draw();
    } finally {
      g.restore();
    }
  }
  camera(c: Camera, draw: () => void) {
    const g = this.g;
    g.save();
    try {
      g.translate(this.width / 2, this.height * 0.42);
      g.scale(c.zoom, c.zoom);
      g.translate(-c.x, -c.y);
      draw();
    } finally {
      g.restore();
    }
  }
  worldRect(rect: Rect): Rect {
    const m = this.g.getTransform(),
      p = [
        [rect.x, rect.y],
        [rect.x + rect.w, rect.y],
        [rect.x, rect.y + rect.h],
        [rect.x + rect.w, rect.y + rect.h],
      ].map(([x, y]) => ({
        x: m.a * x + m.c * y + m.e,
        y: m.b * x + m.d * y + m.f,
      }));
    const xs = p.map((p) => p.x),
      ys = p.map((p) => p.y);
    return {
      x: Math.min(...xs),
      y: Math.min(...ys),
      w: Math.max(...xs) - Math.min(...xs),
      h: Math.max(...ys) - Math.min(...ys),
    };
  }
  bounds(rect: Rect, kind: "text" | "subjects" = "subjects") {
    if (!this.tracking || this.g.globalAlpha < 0.025) return;
    let r = this.worldRect(rect);
    for (const c of this.clips) {
      const x = Math.max(r.x, c.x),
        y = Math.max(r.y, c.y);
      r = {
        x,
        y,
        w: Math.max(0, Math.min(r.x + r.w, c.x + c.w) - x),
        h: Math.max(0, Math.min(r.y + r.h, c.y + c.h) - y),
      };
    }
    if (r.w && r.h) this.layoutData[kind].push({ ...r, name: rect.name });
  }
  clip(path: () => void, rect: Rect, draw: () => void) {
    const g = this.g;
    g.save();
    path();
    g.clip();
    this.clips.push(this.worldRect(rect));
    try {
      draw();
    } finally {
      this.clips.pop();
      g.restore();
    }
  }
  shadow(lift = 2) {
    const g = this.g;
    g.shadowColor = "rgba(38,35,28,.23)";
    g.shadowBlur = 3 + lift * 0.7;
    g.shadowOffsetX = 1 + lift * 0.15;
    g.shadowOffsetY = 2 + lift * 0.5;
  }
  image(id: string, p: Pose & { w: number; anchor?: Point; lift?: number }) {
    const im = this.images[id];
    if (!im) throw Error(`未登记素材 ${id}`);
    const h = (p.w * im.height) / im.width,
      a = p.anchor || this.assets[id].registration?.pivot || { x: 0.5, y: 0.5 };
    this.group(p, () => {
      this.shadow(p.lift ?? 3);
      this.g.drawImage(im, -p.w * a.x, -h * a.y, p.w, h);
      const e = this.extents[id];
      this.bounds({
        x: p.w * (e.x - a.x),
        y: h * (e.y - a.y),
        w: p.w * e.w,
        h: h * e.h,
        name: id,
      });
    });
  }
  anchor(id: string, w: number, name: string): Point {
    const a = this.assets[id].registration?.anchors?.[name];
    if (!a) throw Error(`缺少连接点 ${id}.${name}`);
    const pivot = this.assets[id].registration?.pivot || { x: 0.5, y: 0.5 },
      im = this.images[id];
    return {
      x: (a.x - pivot.x) * w,
      y: ((a.y - pivot.y) * w * im.height) / im.width,
    };
  }
  text(
    text: string,
    x: number,
    y: number,
    size = 26,
    color = "#254a48",
    options: {
      align?: CanvasTextAlign;
      weight?: number;
      screen?: boolean;
    } = {},
  ) {
    const g = this.g;
    g.save();
    g.shadowColor = "transparent";
    g.font = `${options.weight || 600} ${size}px "Kaiti SC","STKaiti",serif`;
    g.textAlign = options.align || "center";
    g.textBaseline = "middle";
    g.fillStyle = color;
    g.fillText(text, x, y);
    const m = g.measureText(text),
      w = m.width;
    this.bounds(
      {
        x:
          x -
          (g.textAlign === "center" ? w / 2 : g.textAlign === "right" ? w : 0),
        y: y - size * 0.62,
        w,
        h: size * 1.24,
        name: text,
      },
      "text",
    );
    g.restore();
  }
  edge(x: number, y: number, w: number, h: number, seed = 1, rough = 4) {
    const g = this.g,
      n = Math.max(7, Math.round(w / 28));
    g.beginPath();
    g.moveTo(x, y);
    for (let i = 1; i <= n; i++)
      g.lineTo(x + (w * i) / n, y + (hash(seed + i) - 0.5) * rough);
    for (let i = 1; i <= 7; i++)
      g.lineTo(x + w + (hash(seed + 50 + i) - 0.5) * rough, y + (h * i) / 7);
    for (let i = n - 1; i >= 0; i--)
      g.lineTo(x + (w * i) / n, y + h + (hash(seed + 100 + i) - 0.5) * rough);
    for (let i = 6; i >= 1; i--)
      g.lineTo(x + (hash(seed + 150 + i) - 0.5) * rough, y + (h * i) / 7);
    g.closePath();
  }
  paper(
    p: Pose & {
      w: number;
      h: number;
      color?: string;
      seed?: number;
      lift?: number;
      name?: string;
    },
  ) {
    this.group(p, () => {
      const g = this.g,
        seed = p.seed || 1;
      this.shadow(p.lift ?? 2);
      this.edge(-p.w / 2, -p.h / 2, p.w, p.h, seed);
      g.fillStyle = p.color || "#f4ead7";
      g.fill();
      g.shadowColor = "transparent";
      g.strokeStyle = "#fff9eb99";
      g.lineWidth = 1.3;
      g.stroke();
      this.bounds({
        x: -p.w / 2,
        y: -p.h / 2,
        w: p.w,
        h: p.h,
        name: p.name || "paper",
      });
      this.clip(
        () => this.edge(-p.w / 2, -p.h / 2, p.w, p.h, seed),
        { x: -p.w / 2, y: -p.h / 2, w: p.w, h: p.h },
        () => {
          g.globalAlpha *= 0.09;
          for (let i = 0; i < (p.w * p.h) / 190; i++) {
            g.fillStyle = i % 3 ? "#816e52" : "#fffdf5";
            g.fillRect(
              (hash(seed + i * 3) - 0.5) * p.w,
              (hash(seed + i * 7) - 0.5) * p.h,
              0.7 + hash(i) * 2,
              0.5,
            );
          }
        },
      );
    });
  }
  background() {
    const g = this.g;
    g.fillStyle = "#e9e4d8";
    g.fillRect(0, 0, this.width, this.height);
    g.save();
    for (let i = 0; i < 2200; i++) {
      g.globalAlpha = 0.025 + hash(i) * 0.04;
      g.fillStyle = i % 4 ? "#79745f" : "#ffffff";
      g.fillRect(
        hash(i + 8) * this.width,
        hash(i + 14) * this.height,
        0.6 + hash(i + 9) * 3,
        0.8,
      );
    }
    g.restore();
  }
}
