// Original MAC media study: one seed travels through seven material worlds.
// No medical anatomy, doctor identity, narration or brand is embedded here.
import { mount } from "./kit/player";
import { phase, mix, arc, onTwos } from "./kit/motion";
import { cameraTrack, settle, hingeRise } from "./kit/tracks";
import { measurePath, pointAt, trace, type PathCommand } from "./kit/paths";
import { cutout, tornEllipse, tape, wash, grain, halftone } from "./kit/materials";
import type { Stage } from "./kit/stage";
import type { Shot, Score, Point } from "./kit/types";
import scoreData from "../score.json";
const score = scoreData as unknown as Score;
const palette = { ink:"#304c49", moss:"#67855b", lime:"#b8bd75", rust:"#b97153", cream:"#f3e7cc" };
const stemCommands: PathCommand[] = [
 {op:"M",x:0,y:0},{op:"C",c1x:4,c1y:-70,c2x:-12,c2y:-126,x:2,y:-215},
 {op:"M",x:0,y:-92},{op:"Q",cx:-70,cy:-99,x:-104,y:-154},
 {op:"M",x:1,y:-157},{op:"Q",cx:68,cy:-157,x:112,y:-221},
];
const stem = measurePath(stemCommands);
const leaf = (side:number,seed=1):Point[] => Array.from({length:50},(_,i)=> {
 const a=i*Math.PI*2/50, r=1+(Math.sin(a*2)*.06)+(Math.sin(i*19+seed)*.02);
 return {x:side*(48+Math.cos(a)*49)*r,y:-24+Math.sin(a)*25*r-Math.cos(a)*26};
});
function inkStem(g:CanvasRenderingContext2D,p=1,color=palette.ink,width=4) {
 g.save();g.strokeStyle=color;g.lineWidth=width;g.lineCap="round";g.lineJoin="round";trace(g,stem,p);g.restore();
}
function vein(g:CanvasRenderingContext2D,side:number) {
 g.save();g.strokeStyle="#f1e4bd99";g.lineWidth=1.7;g.beginPath();g.moveTo(0,0);g.quadraticCurveTo(side*45,-26,side*93,-48);g.stroke();
 for(let j=1;j<5;j++){g.beginPath();g.moveTo(side*j*18,-j*9);g.lineTo(side*(j*18+8),-j*9-14);g.stroke();}g.restore();
}
function seed(s:Stage,x:number,y:number,scale=1,color="#b97a51") {
 cutout(s,{x,y,rotation:-.38,scale},tornEllipse(17,26,33,1.2),color,8,1.5);
 s.group({x,y,rotation:-.38,scale},()=>{const g=s.g;g.strokeStyle="#69482c99";g.lineWidth=1.4;g.beginPath();g.moveTo(-3,-14);g.quadraticCurveTo(8,2,0,18);g.stroke();});
}
function pot(s:Stage,x:number,y:number,front=false) {
 const points=front?[{x:-90,y:-15},{x:88,y:-15},{x:68,y:115},{x:-68,y:115}]:[{x:-91,y:-18},{x:90,y:-18},{x:82,y:20},{x:-83,y:20}];
 cutout(s,{x,y},points,front?palette.rust:"#4e4939",19,2);
 if(front) s.group({x,y},()=>{const g=s.g;g.strokeStyle="#edd0a799";g.lineWidth=2;g.beginPath();g.moveTo(-62,10);g.lineTo(-49,92);g.moveTo(64,9);g.lineTo(51,92);g.stroke();tape(s,{x:0,y:40,rotation:-.08},46,16);});
}
function heading(s:Stage,clean:boolean,label:string,sub:string) {
 if(clean)return;
 s.text(label,100,57,29,palette.ink,{align:"left",weight:600});
 s.text(sub,100,93,18,"#736b5c",{align:"left",weight:400});
}
const push = cameraTrack([{time:0,value:{x:640,y:302.4,zoom:1}},
 {time:4,value:{x:654,y:310,zoom:1.055}},{time:8,value:{x:656,y:306,zoom:1.055}}]);
const shots:Shot[] = [
 {id:"collage",camera:({t})=>push(t),render({stage:s,t,beat,clean}) {
  const g=s.g, qt=onTwos(t), arrive=beat.events.plant;
  // A real paper desk: soil packet, pot rim, independent foreground leaf and labels.
  s.paper({x:337,y:352,w:175,h:230,rotation:-.13,color:"#d9c795",seed:44,name:"seed-packet"});
  s.group({x:337,y:352,rotation:-.13},()=>{cutout(s,{x:0,y:-27},leaf(1,12),palette.moss,11);tape(s,{x:4,y:-109,rotation:.13},66,22);});
  pot(s,669,425);
  const p=arc({x:355,y:305},{x:669,y:427},phase(qt,beat.events.travel,arrive),125);
  if(t<arrive) seed(s,p.x,p.y,1.2);
  s.group({x:669,y:426,rotation:settle(qt,arrive,.025)},()=>{
   const growth=phase(qt,arrive+.2,beat.events.bloom);
   inkStem(g,growth,palette.moss,6);
   const openL=phase(qt,arrive+.75,arrive+1.8),openR=phase(qt,arrive+1.4,beat.events.bloom);
   s.group({x:0,y:-93,rotation:(1-openL)*.8,scale:Math.max(.01,openL)},()=>{cutout(s,{x:0,y:0},leaf(-1,2),palette.moss,3);vein(g,-1);});
   s.group({x:0,y:-157,rotation:-(1-openR)*.8,scale:Math.max(.01,openR)},()=>{cutout(s,{x:0,y:0},leaf(1,6),palette.lime,6);vein(g,1);});
  });
  pot(s,669,425,true);
  cutout(s,{x:1040,y:560,rotation:.35,scale:1.6},leaf(-1,77),"#536f60",77,8);
  s.group({x:928,y:490,rotation:.18},()=>{cutout(s,{x:0,y:0},tornEllipse(56,18,81),"#a9bac0",55,4);cutout(s,{x:55,y:0},[{x:0,y:-7},{x:100,y:-7},{x:107,y:8},{x:0,y:8}],"#a98459",42,3);});
  heading(s,clean,"纸拼贴 · 一粒种子的旅程","物件接触、遮挡与展开，让画面自己讲故事");
 }},
 {id:"watercolor",render({stage:s,t,beat,clean}) {
  const g=s.g;
  g.fillStyle="#f6efd9";g.fillRect(0,0,s.width,s.height);
  s.group({x:640,y:462},()=>{
   // Several separate translucent washes, with pigment boundaries and dry-brush gaps.
   wash(g,[{x:-105,y:-8},{x:105,y:-8},{x:71,y:110},{x:-72,y:110}],"#ad6548",phase(t,0,.9),3);
   inkStem(g,phase(t,.65,beat.events.ink),"#657460",2.5);
   s.group({x:0,y:-93},()=>wash(g,leaf(-1),"#507561",phase(t,beat.events.wash,3.3),22));
   s.group({x:0,y:-157},()=>wash(g,leaf(1),"#99a449",phase(t,2.6,beat.events.bloom),33));
   s.group({x:0,y:10},()=>wash(g,tornEllipse(77,15,28),"#665347",phase(t,.4,1.1),9));
   g.save();g.strokeStyle="#86614b";g.globalAlpha=.45;g.lineWidth=1.6;
   g.beginPath();g.moveTo(-100,-6);g.lineTo(-71,109);g.lineTo(69,108);g.lineTo(101,-6);g.stroke();g.restore();
   if(t>3.3) s.group({x:0,y:-93},()=>vein(g,-1));
  });
  s.group({x:865,y:538,rotation:-.5},()=>{cutout(s,{x:0,y:0},[{x:-7,y:-130},{x:7,y:-130},{x:5,y:0},{x:-5,y:0}],"#ab855a",1,1);cutout(s,{x:0,y:-137},tornEllipse(8,26,9),"#665347",2,1);});
  heading(s,clean,"水彩与墨 · 生长留下笔触","逐笔叠色、积色边缘与干刷，而非整图淡入");
 }},
 {id:"line_art",camera:({t})=>cameraTrack([{time:0,value:{x:640,y:302.4,zoom:1}},
  {time:3,value:{x:640,y:286,zoom:1.12}},{time:7,value:{x:640,y:302.4,zoom:1}}])(t),render({stage:s,t,beat,clean}) {
  const g=s.g;
  seed(s,640,550,.75);
  const line=measurePath([{op:"M",x:565,y:520},{op:"L",x:540,y:417},
   {op:"Q",cx:640,cy:387,x:740,y:417},{op:"L",x:715,y:520},{op:"Q",cx:640,cy:541,x:565,y:520},
   {op:"M",x:640,y:419},{op:"C",c1x:650,c1y:343,c2x:619,c2y:287,x:642,y:206},
   {op:"C",c1x:570,c1y:295,c2x:553,c2y:346,x:640,y:327},
   {op:"C",c1x:726,c1y:307,c2x:738,c2y:235,x:642,y:267}]);
  const p=phase(t,beat.events.draw,beat.events.complete);
  g.strokeStyle=palette.ink;g.lineWidth=3.8;g.lineCap="round";g.lineJoin="round";trace(g,line,p);
  if(p>0&&p<1){const tip=pointAt(line,p);g.fillStyle=palette.rust;g.beginPath();g.arc(tip.x,tip.y,4,0,Math.PI*2);g.fill();}
  s.bounds({x:540,y:203,w:204,h:340,name:"drawn-plant"});
  heading(s,clean,"线条 · 一笔建立关系","按路径长度前进，抬笔处不产生无意义连接线");
 }},
 {id:"scientific_diagram",render({stage:s,t,beat,clean}) {
  const g=s.g, focus=phase(t,beat.events.focus,beat.events.focused);
  s.group({x:540,y:430},()=>{
   inkStem(g,1,palette.moss,4);
   cutout(s,{x:0,y:-93},leaf(-1),palette.moss,23,0);
   cutout(s,{x:0,y:-157},leaf(1),palette.lime,28,0);
   g.fillStyle="#9c765b";g.beginPath();g.moveTo(-90,-10);g.lineTo(90,-10);g.lineTo(68,110);g.lineTo(-68,110);g.closePath();g.fill();
   const root=measurePath([{op:"M",x:0,y:0},{op:"Q",cx:4,cy:40,x:-16,y:95},{op:"M",x:0,y:30},{op:"Q",cx:39,cy:40,x:48,y:78},
    {op:"M",x:-7,y:60},{op:"Q",cx:-35,cy:66,x:-45,y:90}]);
   g.strokeStyle="#e9dcc1";g.lineWidth=3;trace(g,root,1);
   // Tracers represent an authored transport diagram, not a simulated biological model.
   for(let i=0;i<4;i++){const p=pointAt(root,1-((t*.22+i/4)%1));g.fillStyle="#89bbca";g.beginPath();g.arc(p.x,p.y,3,0,Math.PI*2);g.fill();}
  });
  if(focus>0) {
   g.save();g.globalAlpha=focus;g.strokeStyle="#7c9da3";g.lineWidth=1.5;
   g.beginPath();g.moveTo(570,450);g.lineTo(775,395);g.stroke();
   s.group({x:891,y:368,scale:.85+.15*focus},()=>{
    g.fillStyle="#f1ecda";g.beginPath();g.arc(0,0,105,0,Math.PI*2);g.fill();g.stroke();g.save();g.clip();
    g.strokeStyle="#c9b7a0";g.lineWidth=1.4;
    for(let i=-3;i<4;i++)for(let j=-3;j<4;j++){g.strokeRect(i*46+(j%2)*23,j*40,43,37);}
    g.strokeStyle="#7f9e8a";g.lineWidth=20;g.beginPath();g.moveTo(0,110);g.lineTo(0,-110);g.stroke();
    for(let i=0;i<5;i++){const y=105-((t*60+i*44)%220);g.fillStyle="#6da8bb";g.beginPath();g.arc(0,y,5,0,Math.PI*2);g.fill();}g.restore();
   });g.restore();
  }
  heading(s,clean,"科学图示 · 局部才需要解释","切面、定位与局部放大；素材意义仍需专业审查");
 }},
 {id:"whiteboard",render({stage:s,t,beat,clean}) {
  const g=s.g;g.fillStyle="#f7f6ef";g.fillRect(0,0,s.width,s.height);
  seed(s,640,566,.6);
  const potLine=measurePath([{op:"M",x:550,y:440},{op:"L",x:730,y:440},{op:"L",x:706,y:541},{op:"L",x:577,y:541},{op:"L",x:550,y:440}]);
  const p=phase(t,beat.events.draw,1.4);g.strokeStyle="#375b60";g.lineWidth=5;g.lineCap="round";trace(g,potLine,p);
  s.group({x:640,y:440},()=>{
   inkStem(g,phase(t,1.2,2.5),"#557b51",5);
   for(const [side,y] of [[-1,-93],[1,-157]]) {
    const outline=measurePath(leaf(side).map((p,i)=>({op:i===0?"M":"L",x:p.x,y:p.y})));
    s.group({x:0,y},()=>trace(g,outline,phase(t,side<0?2.3:2.7,beat.events.complete)));
   }
  });
  const ring=measurePath([{op:"M",x:528,y:262},{op:"C",c1x:504,c1y:140,c2x:792,c2y:122,x:784,y:296},
   {op:"C",c1x:730,c1y:380,c2x:526,c2y:369,x:528,y:262}]);
  g.strokeStyle="#b76c45";g.lineWidth=3;trace(g,ring,phase(t,beat.events.circle,4.9));
  if(t>beat.events.wipe){g.save();g.beginPath();g.rect(490,120,340*phase(t,beat.events.wipe,6.7),255);g.clip();g.fillStyle="#f7f6ef";g.fillRect(490,120,340,255);g.restore();}
  s.bounds({x:510,y:163,w:280,h:384,name:"marker-plant"});
  heading(s,clean,"白板 · 先建立，再聚焦","笔顺、强调与有目的的擦除；无需悬浮手掌");
 }},
 {id:"risograph",render({stage:s,t,beat,clean}) {
  const g=s.g;g.fillStyle="#ede5cf";g.fillRect(0,0,s.width,s.height);
  seed(s,459,522,.75,"#b88757");
  s.group({x:640,y:444},()=>{
   const blue=phase(t,beat.events.blue,2),red=phase(t,beat.events.red,beat.events.registered);
   const plate=(color:string,offset:Point,p:number)=>{
    g.save();g.translate(offset.x,offset.y);g.beginPath();g.rect(-150,-285,300*p,430);g.clip();
    g.globalAlpha*=.76;g.fillStyle=color;g.beginPath();g.moveTo(-92,0);g.lineTo(92,0);g.lineTo(68,112);g.lineTo(-68,112);g.closePath();g.fill();
    inkStem(g,1,color,6);
    for(const [side,y] of [[-1,-93],[1,-157]]){g.save();g.translate(0,y);g.beginPath();leaf(side).forEach((p,i)=>i?g.lineTo(p.x,p.y):g.moveTo(p.x,p.y));g.closePath();g.clip();g.fillStyle=color;g.globalAlpha=.62;g.fillRect(-110,-90,220,130);g.globalAlpha=1;halftone(g,220,180,color,8,1.7);g.restore();}
    g.restore();
   };
   plate("#508d9b",{x:-2.5,y:0},blue);
   g.save();g.globalCompositeOperation="multiply";plate("#e29763",{x:3.5,y:2.2},red);g.restore();
   grain(g,330,410,271,.08,500);
  });
  heading(s,clean,"Riso · 两张色版相遇","固定套印偏差、半色调与叠色；错版不逐帧乱跳");
 }},
 {id:"paper_popup",camera:({t})=>cameraTrack([{time:0,value:{x:640,y:302.4,zoom:1}},
  {time:3,value:{x:640,y:322,zoom:1.065}},{time:7,value:{x:640,y:322,zoom:1.065}}])(t),render({stage:s,t,beat,clean}) {
  const g=s.g, p=phase(t,beat.events.open,beat.events.opened);
  s.group({x:640,y:511},()=>{
   s.paper({x:-173,y:0,w:350,h:155,rotation:-.08,color:"#ead7b3",seed:8,name:"left-page"});
   s.paper({x:173,y:0,w:350,h:155,rotation:.08,color:"#f3e5c8",seed:19,name:"right-page"});
   g.strokeStyle="#bda27b";g.lineWidth=2;g.beginPath();g.moveTo(0,-76);g.lineTo(0,75);g.stroke();
   const risen=hingeRise(t,beat.events.open,beat.events.opened,{x:0,y:-14});
   // 2D projection of a bottom-hinged paper stage. Tabs remain at the base.
   g.save();g.translate(risen.x,risen.y);g.scale(1,risen.squash);
   g.globalAlpha=risen.opacity??1;
   cutout(s,{x:0,y:-123},[{x:-177,y:109},{x:-177,y:-128},{x:0,y:-214},{x:177,y:-128},{x:177,y:109}],"#acbba4",56,9);
   g.strokeStyle="#f4e8ce";g.lineWidth=6;
   g.beginPath();g.moveTo(-137,-12);g.lineTo(-137,-118);g.lineTo(0,-184);g.lineTo(137,-118);g.lineTo(137,-12);g.moveTo(0,-184);g.lineTo(0,-13);g.moveTo(-138,-91);g.lineTo(138,-91);g.stroke();
   g.restore();
   s.group({x:0,y:-3,scale:1},()=>{g.save();g.scale(1,Math.sin(p*Math.PI/2));
    inkStem(g,1,palette.moss,5);
    cutout(s,{x:0,y:-93},leaf(-1),palette.moss,34,7);cutout(s,{x:0,y:-157},leaf(1),palette.lime,35,7);g.restore();});
   cutout(s,{x:0,y:0},[{x:-85,y:0},{x:85,y:0},{x:63,y:54},{x:-63,y:54}],palette.rust,78,5);
   tape(s,{x:-72,y:22,rotation:-.12},40,9);tape(s,{x:73,y:22,rotation:.12},40,10);
  });
  heading(s,clean,"纸立体书 · 翻开一个小世界","底部折轴、固定纸脚与前后遮挡 · Canvas 2.5D 投影");
 }}
];
mount({assets:[],score,shots});
