import { hash, clamp } from "./motion.ts";
import type { Stage } from "./stage";
import type { Point, Pose } from "./types";

// All marks are stable in object space. Re-seeking cannot change the paper grain.
export function grain(g: CanvasRenderingContext2D, w: number, h: number, seed = 1,
  amount = .08, density = 450) {
  g.save();
  for (let i = 0; i < density; i++) {
    g.fillStyle = i % 3 ? `rgba(73,61,43,${amount})` : `rgba(255,255,244,${amount})`;
    const x = (hash(seed+i*7)-.5)*w, y = (hash(seed+i*11)-.5)*h;
    g.fillRect(x,y,.6+hash(i)*2.2,.5+hash(i+33)*.8);
  }
  g.restore();
}
export function tape(s: Stage, pose: Pose, w = 58, seed = 1) {
  s.group(pose, () => {
    const g = s.g;
    s.shadow(.4);
    s.edge(-w/2,-10,w,20,seed,3.5);
    g.fillStyle = "rgba(237,201,129,.62)"; g.fill();
    g.shadowColor = "transparent";
    g.strokeStyle = "rgba(255,252,231,.4)"; g.lineWidth = .7; g.stroke();
    grain(g,w,18,seed,.1,50);
  });
}
export function cutout(s: Stage, pose: Pose, contour: readonly Point[], color: string,
  seed = 1, lift = 3) {
  s.group(pose, () => {
    const g = s.g;
    const shape = () => {g.beginPath(); contour.forEach((p,i)=>i?g.lineTo(p.x,p.y):g.moveTo(p.x,p.y));g.closePath();};
    s.shadow(lift); shape(); g.fillStyle=color;g.fill(); g.shadowColor="transparent";
    g.strokeStyle="rgba(255,249,230,.8)";g.lineWidth=2;g.stroke();
    const xs=contour.map(p=>p.x),ys=contour.map(p=>p.y);
    const bounds={x:Math.min(...xs),y:Math.min(...ys),w:Math.max(...xs)-Math.min(...xs),h:Math.max(...ys)-Math.min(...ys)};
    s.clip(shape,bounds,()=> {g.translate(bounds.x+bounds.w/2,bounds.y+bounds.h/2);grain(g,bounds.w,bounds.h,seed,.1);});
    s.bounds(bounds);
  });
}
export function tornEllipse(rx: number, ry: number, seed = 1, rough = 2): Point[] {
  return Array.from({length:72},(_,i)=>{
    const a=i*Math.PI*2/72, d=(hash(seed+i)-.5)*rough;
    return {x:Math.cos(a)*(rx+d),y:Math.sin(a)*(ry+d)};
  });
}
export function halftone(g: CanvasRenderingContext2D, w: number, h: number,
  color: string, spacing = 9, radius = 1.7) {
  g.save(); g.fillStyle=color;
  for(let y=-h/2;y<h/2;y+=spacing) for(let x=-w/2;x<w/2;x+=spacing) {
    g.beginPath();g.arc(x+((Math.round(y/spacing)&1)?spacing/2:0),y,radius,0,Math.PI*2);g.fill();
  }
  g.restore();
}
// Wet-on-dry ribbons reveal by distance across the shape; pigment is layered,
// with a stable darker edge and gaps. It is a stylized Canvas wash, not fluid simulation.
export function wash(g: CanvasRenderingContext2D, contour: readonly Point[],
  color: string, p: number, seed = 1) {
  const xs=contour.map(p=>p.x),ys=contour.map(p=>p.y);
  const l=Math.min(...xs),r=Math.max(...xs),top=Math.min(...ys),bottom=Math.max(...ys);
  g.save();g.beginPath();contour.forEach((v,i)=>i?g.lineTo(v.x,v.y):g.moveTo(v.x,v.y));g.closePath();g.clip();
  g.beginPath();g.rect(l,top,(r-l)*clamp(p),bottom-top);g.clip();
  g.fillStyle=color; const alpha=g.globalAlpha;
  for(let i=0;i<18;i++) {
    g.globalAlpha=alpha*(.06+hash(seed+i)*.06);
    g.beginPath();g.ellipse(l+(r-l)*(i+.5)/18, (top+bottom)/2+(hash(seed+i+90)-.5)*12,
      (r-l)/5,(bottom-top)*(.42+hash(i+seed)*.08), (hash(i)-.5)*.1,0,Math.PI*2);g.fill();
  }
  g.globalAlpha=alpha*.24;g.strokeStyle=color;g.lineWidth=3;
  g.beginPath();contour.forEach((v,i)=>i?g.lineTo(v.x,v.y):g.moveTo(v.x,v.y));g.closePath();g.stroke();
  g.globalAlpha=alpha*.25;g.fillStyle="#fff8e5";
  for(let i=0;i<140;i++) g.fillRect(l+hash(i+seed)* (r-l),top+hash(i*13+seed)*(bottom-top),2+hash(i)*8,.8);
  g.restore();
}
