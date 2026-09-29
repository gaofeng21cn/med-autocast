(() => {
  const hash = seed => {
    const n = Math.sin(seed * 127.13 + 41.17) * 43758.55;
    return n - Math.floor(n);
  };

  function create(g) {
    const images = {}, extents = {};
    let text = [], subjects = [], enabled = true;
    const clips = [];

    function reset() { text = []; subjects = []; clips.length = 0; enabled = true; }
    function track(value) { enabled = value; }
    function bounds(x, y, w, h, name, kind = 'object') {
      if (!enabled || g.globalAlpha < .025) return;
      const m = g.getTransform();
      const points = [[x,y],[x+w,y],[x,y+h],[x+w,y+h]].map(([a,b]) =>
        [m.a*a+m.c*b+m.e, m.b*a+m.d*b+m.f]);
      const xs=points.map(p=>p[0]), ys=points.map(p=>p[1]);
      let left=Math.min(...xs),top=Math.min(...ys),right=Math.max(...xs),bottom=Math.max(...ys);
      for (const c of clips) {
        left=Math.max(left,c.x);top=Math.max(top,c.y);
        right=Math.min(right,c.x+c.w);bottom=Math.min(bottom,c.y+c.h);
      }
      if(right>left && bottom>top) (kind==='text'?text:subjects).push({name,x:left,y:top,w:right-left,h:bottom-top});
    }
    function txt(s,x,y,size=24,color='#283936',align='center',weight=600) {
      g.save();g.font=`${weight} ${size}px "Kaiti SC","STKaiti",serif`;
      g.fillStyle=color;g.textAlign=align;g.textBaseline='middle';g.fillText(s,x,y);
      const w=g.measureText(s).width;
      bounds(align==='left'?x:align==='right'?x-w:x-w/2,y-size*.62,w,size*1.24,s,'text');
      g.restore();
    }
    function image(name,x,y,w,angle=0,opacity=1,shadow=7) {
      const im=images[name];if(!im || opacity<=0)return;
      const h=w*im.height/im.width;
      g.save();g.globalAlpha*=opacity;g.translate(x,y);g.rotate(angle);
      if(shadow){g.shadowColor='rgba(25,39,38,.25)';g.shadowBlur=shadow*1.7;g.shadowOffsetY=shadow*.8;g.shadowOffsetX=shadow*.25;}
      g.drawImage(im,-w/2,-h/2,w,h);
      const a=extents[name];
      bounds(-w/2+w*a.x,-h/2+h*a.y,w*a.w,h*a.h,name);g.restore();
    }
    function cutPath(x,y,w,h,seed=1,rough=4) {
      const n=Math.max(7,Math.round(w/32));g.beginPath();g.moveTo(x,y);
      for(let i=1;i<=n;i++)g.lineTo(x+w*i/n,y+(hash(seed+i)-.5)*rough);
      for(let i=1;i<=7;i++)g.lineTo(x+w+(hash(seed+50+i)-.5)*rough,y+h*i/7);
      for(let i=n-1;i>=0;i--)g.lineTo(x+w*i/n,y+h+(hash(seed+100+i)-.5)*rough);
      for(let i=6;i>=1;i--)g.lineTo(x+(hash(seed+150+i)-.5)*rough,y+h*i/7);g.closePath();
    }
    function sheet(x,y,w,h,color='#f8f0de',seed=1,angle=0,lift=0,name='paper') {
      g.save();g.translate(x,y);g.rotate(angle);
      g.shadowColor='rgba(25,34,32,.25)';g.shadowBlur=6+lift*1.7;g.shadowOffsetY=4+lift;g.shadowOffsetX=2+lift*.4;
      cutPath(-w/2,-h/2,w,h,seed,7);g.fillStyle=color;g.fill();
      g.shadowColor='transparent';g.strokeStyle='rgba(255,255,250,.75)';g.lineWidth=2;g.stroke();
      bounds(-w/2,-h/2,w,h,name);
      g.globalAlpha*=.1;g.fillStyle='#283936';
      for(let i=0;i<Math.round(w*h/5400);i++)g.fillRect((hash(seed*101+i*3)-.5)*w,(hash(seed*103+i*7)-.5)*h,1.5,1.3);
      g.restore();
    }
    function masked(x,y,w,h,render) {
      g.save();g.beginPath();g.rect(x,y,w,h);g.clip();
      const m=g.getTransform();
      const corners=[[x,y],[x+w,y],[x,y+h],[x+w,y+h]].map(([a,b])=>[m.a*a+m.c*b+m.e,m.b*a+m.d*b+m.f]);
      const xs=corners.map(p=>p[0]),ys=corners.map(p=>p[1]);
      clips.push({x:Math.min(...xs),y:Math.min(...ys),w:Math.max(...xs)-Math.min(...xs),h:Math.max(...ys)-Math.min(...ys)});
      try { render(); } finally { clips.pop();g.restore(); }
    }
    function camera({x=640,y=302,zoom=1},render) {
      g.save();g.translate(640,302);g.scale(zoom,zoom);g.translate(-x,-y);
      try { render(); } finally { g.restore(); }
    }
    async function load(paths) {
      await Promise.all(Object.entries(paths).map(([name,src])=>new Promise((resolve,reject)=>{
        const im=new Image();im.onload=()=>{
          images[name]=im;
          // Alpha bounds measure the actual cutout, including rotations, rather than the image's empty margins.
          const c=document.createElement('canvas');c.width=160;c.height=Math.max(1,Math.round(160*im.height/im.width));
          const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(im,0,0,c.width,c.height);
          let pixels;
          try { pixels=ctx.getImageData(0,0,c.width,c.height).data; }
          catch(error) {
            // Local file playback may forbid pixel reads. Rendering is still permitted.
            if(error.name==='SecurityError'){extents[name]={x:0,y:0,w:1,h:1};resolve();return;}
            reject(error);return;
          }
          let left=c.width,top=c.height,right=0,bottom=0;
          for(let y=0;y<c.height;y++)for(let x=0;x<c.width;x++)if(pixels[(y*c.width+x)*4+3]>12){left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x+1);bottom=Math.max(bottom,y+1);}
          extents[name]={x:left/c.width,y:top/c.height,w:(right-left)/c.width,h:(bottom-top)/c.height};resolve();
        };im.onerror=()=>reject(new Error(`素材加载失败: ${src}`));im.src=src;
      })));
    }
    return {images,load,reset,track,bounds,txt,image,cutPath,sheet,masked,camera,
      layout:()=>({subjects,text})};
  }
  window.PaperStage={create};
})();
