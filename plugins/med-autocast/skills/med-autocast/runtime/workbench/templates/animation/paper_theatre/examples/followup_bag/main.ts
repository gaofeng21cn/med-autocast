// Original MAC study, informed by paper-collage-mv's staging methods.
// No upstream code/assets, no author identity. One score clock, random-seek safe.
import { mount } from "./kit/player";
import { phase, mix } from "./kit/motion";
import { track } from "./kit/tracks";
import { cutout, tornEllipse, tape } from "./kit/materials";
import type { Stage } from "./kit/stage";
import type { Score, Shot, Point } from "./kit/types";
import scoreData from "../score.json";
const score = scoreData as unknown as Score;
const col = {paper:"#fbf6e8", ink:"#3a4545", green:"#528573", red:"#b86950", wood:"#c4a273", skin:"#e7bb9b"};
const oval = (s:Stage,x:number,y:number,rx:number,ry:number,color:string,seed=1,lift=2) =>
  cutout(s,{x,y},tornEllipse(rx,ry,seed,.8),color,seed,lift);
function line(s:Stage, pts:Point[], color:string, width=2) {
  const g=s.g;g.save();g.strokeStyle=color;g.lineWidth=width;g.lineCap="round";g.lineJoin="round";
  g.beginPath();pts.forEach((p,i)=>i?g.lineTo(p.x,p.y):g.moveTo(p.x,p.y));g.stroke();g.restore();
}
function pillSheet(s:Stage, x:number,y:number,rotation=0,scale=1) {
  s.group({x,y,rotation,scale},()=>{
    s.paper({x:0,y:0,w:72,h:112,color:"#ede9df",seed:15,lift:4,name:"pill-blister"});
    for(let r=0;r<3;r++)for(let c=0;c<2;c++){
      const g=s.g;g.fillStyle="#b9c8c7";g.beginPath();g.ellipse(-17+c*34,-34+r*34,11,15,0,0,Math.PI*2);g.fill();
      g.fillStyle="#fffdf6";g.beginPath();g.ellipse(-19+c*34,-37+r*34,7,11,0,0,Math.PI*2);g.fill();
    }
  });
}
function bagBack(s:Stage) {
  s.paper({x:0,y:0,w:198,h:157,color:"#8e4f40",seed:71,lift:3,name:"bag-back"});
  line(s,[{x:-35,y:-70},{x:-32,y:-109},{x:34,y:-109},{x:38,y:-70}],"#704838",9);
  s.paper({x:-23,y:-18,w:105,h:113,rotation:-.09,color:"#fff7db",seed:75,name:"appointment-book"});
  line(s,[{x:-63,y:-36},{x:11,y:-36}],"#9aaf9d",3);
  for(let i=0;i<3;i++)line(s,[{x:-61,y:-13+i*13},{x:8,y:-13+i*13}],"#c4beab",1.5);
}
function bagFront(s:Stage,closed:number) {
  cutout(s,{x:0,y:26},[{x:-101,y:-40},{x:-85,y:-30},{x:85,y:-30},{x:100,y:-43},{x:94,y:52},{x:-94,y:52}],col.red,72,4);
  if(closed>0) s.group({x:0,y:-67},()=>{
    s.g.save();s.g.scale(1,closed);
    cutout(s,{x:0,y:0},[{x:-100,y:0},{x:99,y:0},{x:84,y:67},{x:10,y:88},{x:-87,y:65}],"#c77c60",73,4);
    oval(s,0,65,7,7,"#c9b57b",74,.5);s.g.restore();
  });
  line(s,[{x:-83,y:43},{x:82,y:43}],"#ecc6a1",1.2);
}
function room(s:Stage,t:number) {
  const g=s.g;g.fillStyle=col.paper;g.fillRect(-400,-300,2200,1400);
  // Window has a sill, separate panes and a view. It is not a text backing card.
  s.paper({x:235,y:240,w:280,h:317,color:"#e2cdb0",seed:1,lift:2,name:"window-frame"});
  s.paper({x:235,y:231,w:245,h:271,color:"#c6e0dd",seed:2,lift:0,name:"window-sky"});
  oval(s,274,150,37,37,"#f8e8aa",3,0);
  cutout(s,{x:235,y:312},[{x:-117,y:42},{x:-117,y:-15},{x:-45,y:-48},{x:14,y:-11},{x:75,y:-38},{x:120,y:-6},{x:120,y:42}],"#a9c6aa",4,0);
  line(s,[{x:235,y:94},{x:235,y:370}],"#fdf8e6",9);line(s,[{x:113,y:234},{x:357,y:234}],"#fdf8e6",8);
  s.paper({x:236,y:393,w:308,h:26,color:"#e8d9bd",seed:5,lift:4,name:"window-sill"});
  // A house plant has a stem and a pot; no floating decorative stripes.
  line(s,[{x:161,y:378},{x:159,y:307}],"#6f8b66",4);
  for(const [x,y,rot] of [[144,335,-.5],[175,319,.6]]) s.group({x,y,rotation:rot+Math.sin(t*.9)*.018},()=>oval(s,0,0,22,10,"#8ea57d",7));
  cutout(s,{x:160,y:381},[{x:-25,y:-20},{x:26,y:-20},{x:20,y:11},{x:-20,y:11}],"#b58061",8,2);
  // Door on the exit side. Wide trim and knob distinguish it from a plain block.
  s.paper({x:1130,y:343,w:205,h:500,color:"#d8cfb7",seed:10,lift:1,name:"door-frame"});
  s.paper({x:1130,y:340,w:174,h:474,color:"#c8d2b8",seed:11,lift:1,name:"door"});
  line(s,[{x:1070,y:145},{x:1190,y:145},{x:1190,y:315},{x:1070,y:315},{x:1070,y:145}],"#b2bd9e",3);
  oval(s,1070,361,8,8,"#a18355",12,2);
  // Small bedside stool for medicine, not a full-width colour band.
  for(const x of [374,460])s.paper({x,y:543,w:18,h:118,color:col.wood,seed:x,lift:1});
  s.paper({x:417,y:486,w:156,h:28,color:"#d3b789",seed:13,lift:4,name:"medicine-stool"});
  // Packing table stands independently, with its own top edge and legs.
  for(const x of [731,927])s.paper({x,y:600,w:22,h:120,color:"#b39470",seed:x,lift:1});
  cutout(s,{x:829,y:556},[{x:-139,y:-19},{x:147,y:-19},{x:158,y:8},{x:-147,y:8}],"#d8bb91",14,4);
  // Sparse floor scraps describe a wooden floor, away from the main action.
  line(s,[{x:70,y:636},{x:1180,y:636}],"#e4d5ba",2);
  for(let i=0;i<9;i++) line(s,[{x:70+i*135,y:638},{x:20+i*145,y:715}],"#eadfc9",1);
  s.paper({x:837,y:184,w:86,h:90,rotation:-.06,color:"#fff7dc",seed:18,lift:1});
  tape(s,{x:838,y:141,rotation:.11},37,19);
}
// A cut-paper actor for THIS study. Hands are endpoints shared with carried props.
// Sleeves are straight paper pieces; torso/head/eyes move before a reach.
function actorLocal(s:Stage,x:number,y:number,lean:number,left:Point,right:Point,look:number,relaxed:boolean) {
  const turn=(p:Point):Point=>({x:x+p.x*Math.cos(lean)-(p.y+110)*Math.sin(lean),y:y-110+p.x*Math.sin(lean)+(p.y+110)*Math.cos(lean)});
  const shoulderL=turn({x:-29,y:-183}), shoulderR=turn({x:29,y:-183});
  for(const dx of [-22,23]){
    cutout(s,{x:x+dx,y:y-26},[{x:-12,y:-60},{x:13,y:-60},{x:15,y:24},{x:-13,y:24}],"#525c63",41+dx,2);
    oval(s,x+dx+7,y-1,24,10,"#675854",42+dx,2);
  }
  const sleeve=(a:Point,b:Point,seed:number)=>{
    const angle=Math.atan2(b.y-a.y,b.x-a.x),L=Math.hypot(b.x-a.x,b.y-a.y);
    s.group({x:a.x,y:a.y,rotation:angle},()=>cutout(s,{x:0,y:0},[{x:0,y:-16},{x:L-8,y:-12},{x:L-8,y:12},{x:0,y:17}],col.green,seed,3));
  };
  sleeve(shoulderL,left,51);
  s.group({x,y:y-110,rotation:lean},()=>{
    cutout(s,{x:0,y:0},[{x:-40,y:-86},{x:39,y:-86},{x:49,y:35},{x:-52,y:35}],col.green,52,3);
    line(s,[{x:1,y:-64},{x:1,y:31}],"#c1d2ad",2);
    for(let i=0;i<3;i++)oval(s,6,-38+i*22,2.5,2.5,"#eee4bc",53+i,.5);
    oval(s,0,-115,51,55,"#79716a",56,3);
    oval(s,2,-106,43,45,col.skin,57,2);
    cutout(s,{x:0,y:-121},[{x:-47,y:10},{x:-50,y:-11},{x:-34,y:-43},{x:8,y:-49},{x:40,y:-26},{x:49,y:3},{x:20,y:-14},{x:3,y:-7},{x:-18,y:-21},{x:-29,y:6}],"#78716c",58,2);
    for(const dx of [-16,18]){
      oval(s,dx+look*3,-108,3.1,4.6,col.ink,59+dx,.1);
      oval(s,dx+look*3-1,-110,1,1,"#fffdf2",61+dx,.1);
    }
    line(s,[{x:-21,y:-122},{x:-12,y:-123+(relaxed?0:3)}],"#58514c",2);
    line(s,[{x:12,y:-122+(relaxed?0:3)},{x:22,y:-122}],"#58514c",2);
    line(s,[{x:-7,y:-88},{x:0,y:relaxed?-84:-88},{x:8,y:-89}],"#9b6653",1.8);
    oval(s,-28,-96,7,3,"#d69b85",64,.1);
  });
  sleeve(shoulderR,right,65);
  oval(s,left.x,left.y,10,12,col.skin,66,3);
  oval(s,right.x,right.y,10,12,col.skin,67,3);
}
function actor(s:Stage,x:number,y:number,lean:number,left:Point,right:Point,look:number,relaxed:boolean) {
  const size=1.35;
  s.group({x,y,scale:size},()=>actorLocal(s,0,0,lean,
    {x:(left.x-x)/size,y:(left.y-y)/size},
    {x:(right.x-x)/size,y:(right.y-y)/size},look,relaxed));
}
const sheetMode=new URLSearchParams(location.search).get("props")==="1";
const shots:Shot[]=[{id:"packing",depth:"flat",camera:({t,beat})=>sheetMode?{x:640,y:302.4,zoom:1}:track([
  {time:0,value:{x:640,y:302.4,zoom:1}},
  {time:beat.events.notice,value:{x:675,y:368,zoom:1.24}},
  {time:beat.events.turn,value:{x:675,y:368,zoom:1.24}},
  {time:beat.events.grip,value:{x:560,y:382,zoom:1.40}},
  {time:beat.events.handoff,value:{x:630,y:378,zoom:1.45}},
  {time:beat.events.stowed,value:{x:724,y:382,zoom:1.4}},
  {time:beat.events.closed,value:{x:724,y:382,zoom:1.4}},
  {time:beat.events.ready,value:{x:675,y:360,zoom:1.14}},
  {time:11.4,value:{x:640,y:302.4,zoom:1}},
  {time:12,value:{x:640,y:302.4,zoom:1}}
])(t),render({stage:s,t,beat}){
  const e=beat.events;
  if(sheetMode){
    for(const [i,closed] of [0,0,0,1].entries()) s.group({x:185+i*295,y:385,scale:1.04},()=>{
      if(i===0){pillSheet(s,0,0,-.12);return;}
      bagBack(s);if(i<3)pillSheet(s,i===1?-8:8,i===1?-97:0,-.09,.75);bagFront(s,closed);
    });return;
  }
  room(s,t);
  const dx=0; // The result is a packed bag ready at the door; no sliding walk cycle.
  const lean=mix(.065,-.13,phase(t,e.notice,e.turn))+phase(t,e.grip,e.handoff)*.15;
  const left=track([
    {time:0,value:{x:563,y:467}},{time:e.turn,value:{x:540,y:460}},
    {time:e.grip-.45,value:{x:540,y:460},ease:"out"},{time:e.grip,value:{x:443,y:467}},
    {time:e.grip+.15,value:{x:443,y:467},ease:"out"},{time:e.handoff-.25,value:{x:600,y:423}},
    {time:e.handoff+.15,value:{x:600,y:423}},{time:e.stowed,value:{x:562,y:468}}
  ])(t);
  const right=track([
    {time:0,value:{x:758,y:441},ease:"out"},{time:e.check,value:{x:800,y:458}},
    {time:e.notice-.15,value:{x:800,y:458},ease:"out"},{time:e.notice,value:{x:716,y:440}},
    {time:e.grip,value:{x:716,y:440}},{time:e.handoff-.25,value:{x:600,y:423}},
    {time:e.handoff+.1,value:{x:600,y:423},ease:"out"},{time:e.stowed-.2,value:{x:808,y:463}},
    {time:e.stowed,value:{x:808,y:485}},{time:e.stowed+.15,value:{x:808,y:485},ease:"out"},
    {time:e.closed-.4,value:{x:815,y:410}},{time:e.closed,value:{x:815,y:440}},
    {time:e.lift-.3,value:{x:815,y:440}},{time:e.lift,value:{x:824,y:350}},
    {time:e.lift+.55,value:{x:784,y:315}}
  ])(t);
  const moving=phase(t,e.lift,e.lift+.55),bag={x:mix(824,784,moving)+dx,y:mix(459,424,moving)};
  // Bag handle is y=-109, so its world endpoint remains exactly on the hand.
  s.group(bag,()=>bagBack(s));
  if(t<e.grip)pillSheet(s,443,432,-.13,.72);
  else if(t<e.stowed){
    const hand=t<e.handoff?left:right;
    pillSheet(s,hand.x+dx,hand.y-34,-.10,.72);
  }else s.group(bag,()=>pillSheet(s,-10,3,-.1,.72));
  actor(s,615+dx,595,lean,{x:left.x+dx,y:left.y},{x:right.x+dx,y:right.y},t<e.notice?1:t<e.handoff?-1:1,t>=e.stowed);
  // Fingers are drawn on top of held paper; the bag lip then occludes entering hands.
  if(t>=e.grip&&t<e.stowed){const h=t<e.handoff?left:right;oval(s,h.x+dx,h.y,10,10,col.skin,68,2);}
  s.group(bag,()=>bagFront(s,phase(t,e.closed-.45,e.closed)));
  // Final hold preserves the packed bag; no new card, title or decorative burst.
}}];
mount({assets:[],score,shots});
