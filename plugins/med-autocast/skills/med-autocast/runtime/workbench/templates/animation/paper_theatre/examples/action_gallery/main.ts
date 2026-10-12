import { mount } from "../../src/kit/player";
import { measurePath } from "../../src/kit/paths";
import { tape } from "../../src/kit/materials";
import {
  cutOpen,
  dropSheet,
  foldPanel,
  liftCorner,
  penStroke,
  pullStrip,
  snapClip,
  tearSheet,
  turnPage,
  unfoldMap,
  unrollTape,
  wrapAround,
} from "../../src/kit/actions";
import type { Camera, Shot, ShotContext, Score } from "../../src/kit/types";
import scoreData from "./score.json";

const score = scoreData as unknown as Score;

// Every sample is a self-contained paper behaviour on a neutral stage. They
// exist to prove the action library renders, not to prescribe a story.
const stage0 = (s: ShotContext["stage"], label: string) => {
  const g = s.g;
  // A real paper stage: torn ground, a working surface, tape, fasteners and
  // depth. An action on an empty field reads as a slide regardless of quality.
  s.paper({ x: 640, y: 300, w: 1360, h: 760, color: "#c9d4cb", seed: 3, lift: 0, name: "ground" });
  s.paper({ x: 640, y: 588, w: 1240, h: 260, color: "#dccdb0", seed: 5, lift: 2, name: "desk" });
  s.group({ x: 1188, y: 560, rotation: 0.05 }, () => tape(s, { x: 0, y: 0 }, 60, 11));
  s.text(label, 640, 640, 26, "#3f4d47");
};

const push = (from: Camera, to: Camera, p: number): Camera => ({
  x: from.x + (to.x - from.x) * p,
  y: from.y + (to.y - from.y) * p,
  zoom: from.zoom + (to.zoom - from.zoom) * p,
});

const shots: Shot[] = [
  {
    id: "tear",
    camera: ({ t }) => ({ x: 640, y: 340, zoom: 1 + Math.min(0.06, t * 0.012) }),
    render({ stage: s, t, beat }) {
      stage0(s, "撕开：同一张纸分成两半，纤维沿缝可见");
      tearSheet(s, t, {
        start: beat.events.start,
        end: beat.events.done,
        x: 640,
        y: 360,
        w: 520,
        h: 320,
        color: "#f2e7cf",
        drawLeft: (st) => {
          st.text("已确认", -130, 0, 34, "#6b5f49");
        },
        drawRight: (st) => {
          st.text("待补", 130, 0, 34, "#a3604c");
        },
      });
    },
  },
  {
    id: "lift",
    camera: ({ t }) => ({ x: 640, y: 330, zoom: 1.05 - Math.min(0.05, t * 0.011) }),
    render({ stage: s, t, beat }) {
      stage0(s, "揭起：离开纸面、越过高度、落到新位置");
      s.paper({ x: 380, y: 400, w: 300, h: 210, color: "#e6dcc2", seed: 12, name: "source" });
      s.text("来源层", 380, 400, 26, "#6b5f49");
      liftCorner(s, t, {
        start: beat.events.start,
        peak: beat.events.peak,
        end: beat.events.end_ev,
        from: { x: 620, y: 400, rotation: -0.03 },
        to: { x: 900, y: 372, rotation: 0.05 },
        w: 250,
        h: 170,
        color: "#cfe0d4",
        lift: 40,
      });
    },
  },
  {
    id: "page",
    camera: ({ t }) => ({ x: 640, y: 340, zoom: 1 + Math.min(0.07, t * 0.014) }),
    render({ stage: s, t, beat }) {
      stage0(s, "翻页：折轴抬起、纸面弯折、影子随高度移动");
      turnPage(s, t, {
        start: beat.events.start,
        end: beat.events.end_ev,
        x: 640,
        y: 360,
        w: 480,
        h: 330,
        color: "#f6efdc",
        face: (st) => {
          st.text("第 2 页", 60, -30, 30, "#5c6a60");
        },
      });
    },
  },
  {
    id: "cut",
    camera: ({ t }) => push({ x: 640, y: 350, zoom: 1.02 }, { x: 640, y: 330, zoom: 1.12 }, Math.min(1, t / 4)),
    render({ stage: s, t, beat }) {
      stage0(s, "剪开：刀路先走，剪断后才分离");
      cutOpen(s, t, {
        start: beat.events.start,
        severAt: beat.events.sever,
        end: beat.events.done,
        x: 640,
        y: 360,
        w: 300,
        h: 300,
        drawTop: (st) => st.paper({ x: 0, y: 0, w: 300, h: 300, color: "#e9dcc0", seed: 21, lift: 3 }),
        drawBottom: (st) => st.paper({ x: 0, y: 0, w: 300, h: 300, color: "#e9dcc0", seed: 22, lift: 1 }),
      });
    },
  },
  {
    id: "tape",
    camera: ({ t }) => ({ x: 640, y: 340, zoom: 1.04 }),
    render({ stage: s, t, beat }) {
      stage0(s, "拉出：卷尺展开、刻度按同一进度生长");
      unrollTape(s, t, {
        start: beat.events.start,
        end: beat.events.done,
        x: 330,
        y: 430,
        length: 640,
        ticks: (st, len) => {
          const g = st.g;
          g.save();
          g.strokeStyle = "#8d7f61";
          g.lineWidth = 1.4;
          for (let i = 1; i * 60 < len; i++) {
            g.beginPath();
            g.moveTo(i * 60, -6);
            g.lineTo(i * 60, 6);
            g.stroke();
          }
          g.restore();
        },
      });
    },
  },
  {
    id: "wrap",
    camera: ({ t }) => ({ x: 640, y: 350, zoom: 1.08 }),
    render({ stage: s, t, beat }) {
      stage0(s, "缠绕：绷带绕主体收紧，接触点真实存在");
      s.group({ x: 640, y: 350 }, () => {
        s.paper({ x: 0, y: 0, w: 320, h: 210, color: "#d9c9a8", seed: 31, lift: 2, name: "subject" });
        s.text("包扎区", 0, 0, 30, "#5f5340");
      });
      wrapAround(s, t, {
        start: beat.events.start,
        end: beat.events.done,
        x: 640,
        y: 350,
        rx: 170,
        ry: 110,
        turns: 2,
      });
    },
  },
  {
    id: "clip",
    camera: ({ t }) => ({ x: 640, y: 350, zoom: 1.16 - Math.min(0.06, t * 0.012) }),
    render({ stage: s, t, beat }) {
      stage0(s, "夹合：夹口合拢并回弹，不是淡出");
      s.paper({ x: 640, y: 400, w: 420, h: 240, color: "#f4ecd8", seed: 41, lift: 2 });
      s.text("待固定", 640, 400, 30, "#5f5340");
      snapClip(s, t, { closeAt: beat.events.close, x: 640, y: 268, scale: 1.5, angle: 0.03 });
    },
  },
  {
    id: "drop",
    camera: ({ t }) => ({ x: 640, y: 340, zoom: 1.03 }),
    render({ stage: s, t, beat }) {
      stage0(s, "落纸：自由落体、触面、回弹衰减到静止");
      dropSheet(s, t, {
        release: beat.events.release,
        impact: beat.events.impact,
        from: { x: 300, y: 120, rotation: -0.2 },
        to: { x: 640, y: 420, rotation: 0.04 },
        w: 260,
        h: 180,
        color: "#dfe7d3",
        face: () => undefined,
      });
    },
  },
  {
    id: "map",
    camera: ({ t }) => ({ x: 640, y: 350, zoom: 1.02 + Math.min(0.05, t * 0.01) }),
    render({ stage: s, t, beat }) {
      stage0(s, "折叠图：多叶按顺序展开，不是整体缩放");
      unfoldMap(s, t, {
        start: beat.events.start,
        end: beat.events.done,
        x: 640,
        y: 370,
        w: 720,
        h: 260,
        panels: 4,
        color: "#eee3c6",
        label: (st, i, open) => {
          if (open > 0.55) st.text(`步骤 ${i + 1}`, 0, -10, 24, "#5d6a5f");
        },
      });
    },
  },
  {
    id: "pen",
    camera: ({ t }) => ({ x: 640, y: 350, zoom: 1.1 }),
    render({ stage: s, t, beat }) {
      stage0(s, "笔迹：抬笔保留，笔尖跟随书写前沿");
      const path = measurePath([
        { op: "M", x: 420, y: 470 },
        { op: "L", x: 620, y: 330 },
        { op: "M", x: 640, y: 330 },
        { op: "C", c1x: 760, c1y: 300, c2x: 840, c2y: 380, x: 880, y: 300 },
      ]);
      penStroke(s, t, { start: beat.events.start, end: beat.events.done, path, color: "#3f514c", width: 4 });
    },
  },
];

mount({ assets: [], score, shots });

