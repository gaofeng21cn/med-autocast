import { mount } from "./kit/player";
import { phase, mix, stampPose, stow } from "./kit/motion";
import { hinge } from "./kit/props";
import type { Shot, Score } from "./kit/types";
import scoreData from "../score.json";
import brand from "../brand.json";
const score = scoreData as unknown as Score;
const shots: Shot[] = [
  {
    id: "fold",
    render({ stage: s, t, beat }) {
      s.paper({ x: 640, y: 322, w: 400, h: 290, seed: 3, color: "#c3d0b3" });
      hinge(s, { x: 438, y: 322 }, 400, 290, phase(t, beat.events.open, beat.events.opened), () =>
        s.paper({ x: 200, y: 0, w: 400, h: 290, seed: 4, color: "#f4ead7" }),
      );
    },
  },
  {
    id: "stow",
    render({ stage: s, t, beat }) {
      s.paper({ x: 640, y: 360, w: 410, h: 270, color: "#be8e64", seed: 9 });
      const p = stow(
        t,
        beat.events.move,
        beat.events.arrive,
        { x: 380, y: 165, rotation: -0.1 },
        { x: 640, y: 360, rotation: 0.03 },
      );
      s.group(p, () =>
        s.paper({ x: 0, y: 0, w: 180, h: 215, color: "#d1d8bc", seed: 22 }),
      );
      s.paper({ x: 640, y: 408, w: 410, h: 174, color: "#bd7054", seed: 10 });
    },
  },
  {
    id: "stamp",
    render({ stage: s, t, beat }) {
      s.paper({ x: 640, y: 355, w: 390, h: 235, seed: 20 });
      const p = stampPose(t, beat.events.contact, beat.events.lift, { x: 640, y: 360 });
      if (p.printed) {
        s.g.strokeStyle = "#b55243";
        s.g.lineWidth = 4;
        s.g.beginPath();
        s.g.ellipse(640, 360, 45, 28, 0, 0, Math.PI * 2);
        s.g.stroke();
      }
      s.group(p, () => {
        s.paper({
          x: 0,
          y: -20,
          w: 115,
          h: 40,
          color: "#466d66",
          seed: 7,
          lift: p.height * 0.06,
        });
        s.paper({
          x: 0,
          y: -100,
          w: 30,
          h: 120,
          color: "#b4895d",
          seed: 8,
          lift: p.height * 0.06,
        });
      });
    },
  },
];
mount({ assets: [], score, shots, brand: brand.enabled ? brand : undefined });
