import type { Stage } from "./stage";
import type { Pose } from "./types";

export type SceneLayer = {
  id: string;
  role: "environment" | "subject" | "foreground";
  trackLayout?: boolean;
  pose?: Pose;
  draw: () => void;
};

// The director owns ordering and composition; layers do not prescribe a shot recipe.
export function scene(stage: Stage, layers: SceneLayer[]) {
  const tracking = stage.tracking;
  for (const layer of layers) {
    stage.tracking = tracking && (layer.trackLayout ?? layer.role !== "environment");
    try {
      stage.group(layer.pose ?? { x: 0, y: 0 }, layer.draw);
    } finally {
      stage.tracking = tracking;
    }
  }
}

export function backdrop(stage: Stage, id: string, x = 640, y = 360, width = 1360) {
  const g = stage.g, image = stage.images[id];
  const height = width * image.height / image.width;
  g.save();
  g.shadowColor = "transparent";
  g.drawImage(image, x - width / 2, y - height / 2, width, height);
  g.restore();
}
