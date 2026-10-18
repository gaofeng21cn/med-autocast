import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
function dependency(name: string) {
  for(const directory of [root,process.env.MED_AUTOCAST_WORKSPACE_ROOT,
    process.env.MED_AUTOCAST_WORKSPACE_ROOT && path.join(process.env.MED_AUTOCAST_WORKSPACE_ROOT,'templates/animation/paper_theatre'),
    ...[1,2,3,4,5,6].map(n=>path.resolve(root,...Array(n).fill('..')))]) {
    if(!directory)continue;
    try{return createRequire(path.join(directory,'package.json'))(name);}catch(e){if((e as any).code!=='MODULE_NOT_FOUND')throw e;}
  }
}
test('显式文字区域：真实字形、换行、变换和放不下的诊断',async t=>{
  const esbuild=dependency('esbuild'),pw=dependency('playwright');
  if(!esbuild||!pw){t.skip('缺少真实 Chromium/esbuild，不能视作像素回归通过');return;}
  const bundle=await esbuild.build({stdin:{resolveDir:root,loader:'ts',contents:`
import {Stage} from './src/kit/stage';
import {textBox,cardTitle} from './src/kit/labels';
export function run(kind) {
 const c=document.createElement('canvas');c.width=800;c.height=600;
 const g=c.getContext('2d');const s=new Stage(g,800,600);let result;
 g.clearRect(0,0,800,600);
 s.group({x:kind==='offscreen'?-25:400,y:300,rotation:kind==='rotated'?.24:0,scale:kind==='rotated'?1.4:1},()=>{
   if(kind.startsWith('raw-')){
     s.text('读数 mmHg',0,0,27,'#254a48',{align:kind.slice(4),region:{x:-230,y:-50,w:460,h:100},owner:'原始绘字真实边界'});
     result={fits:true};
   }
   else if(kind==='stage-label')result=s.label('纸件与标签共用区域',{x:-125,y:-35,w:250,h:70},{size:26});
   else if(kind==='tiny')result=textBox(s,{x:-18,y:-8,w:36,h:16},'不能裁掉医学文字的后半句',{size:24,minSize:20,maxLines:2});
   else if(kind==='top')result=cardTitle(s,250,100,'顶部医学标签',{size:26,y:-40});
   else if(kind==='inset')result=cardTitle(s,245,112,'内分泌检查',{size:26,inset:52});
   else if(kind==='badge')result=cardTitle(s,100,29,'内分泌',{size:18});
   else if(kind==='long')result=cardTitle(s,250,140,'这是需要换行但必须完整保留的中文医学标题',{size:26,minSize:22,maxLines:2});
   else result=cardTitle(s,250,100,'从第一口开始计时',{size:26,minSize:22});
 });
 const layout=s.layout(),r=layout.textRegions[0],data=g.getImageData(0,0,800,600).data;
 let outside=0,ink=0,top=600,bottom=0,left=800,right=0;
 for(let y=0;y<600;y++)for(let x=0;x<800;x++)if(data[(y*800+x)*4+3]>32){
   ink++;top=Math.min(top,y);bottom=Math.max(bottom,y+1);left=Math.min(left,x);right=Math.max(right,x+1);
   if(x<Math.floor(r.ink.x)-1||x>Math.ceil(r.ink.x+r.ink.w)+1||y<Math.floor(r.ink.y)-1||y>Math.ceil(r.ink.y+r.ink.h)+1)outside++;
 }
 return {result,r,ink,outside,bounds:layout.text[0],pixelBounds:{x:left,y:top,w:right-left,h:bottom-top}};
}
`},bundle:true,write:false,format:'iife',globalName:'Fixture',target:'es2022'});
  const browser=await pw.chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
  try {
    const page=await browser.newPage();await page.setContent('<!doctype html><meta charset=utf-8>');
    await page.addScriptTag({content:bundle.outputFiles[0].text});await page.evaluate(()=>document.fonts.ready);
    const rows=await page.evaluate(()=>Object.fromEntries(['normal','rotated','long','tiny','badge','top','inset','offscreen','stage-label','raw-left','raw-center','raw-right'].map(kind=>[kind,(window as any).Fixture.run(kind)])));
    for(const kind of ['normal','rotated','long','badge','top','inset','stage-label','raw-left','raw-center','raw-right']){
      assert.equal(rows[kind].result.fits,true,kind);assert.ok(rows[kind].ink>0);assert.equal(rows[kind].outside,0,kind);
    }
    assert.ok(rows.offscreen.bounds.x<0,'offscreen paper labels must leave with their owner');
    assert.ok(Math.abs(rows.offscreen.bounds.x-(rows.normal.bounds.x-425))<1,'do not clamp text independently of its paper');
    assert.equal(rows.long.result.lines.join(''),'这是需要换行但必须完整保留的中文医学标题');
    assert.equal(rows.tiny.result.lines.join(''),'不能裁掉医学文字的后半句');
    assert.equal(rows.tiny.result.fits,false);assert.equal(rows.tiny.r.size,20);
    assert.ok(Object.values(rows.tiny.r.overflow).some(v=>(v as number)>0));
    for(const kind of ['raw-left','raw-center','raw-right']){
      assert.ok(Math.abs(rows[kind].bounds.h-rows[kind].pixelBounds.h)<=3,kind+' must use actual glyph height');
      assert.ok(Math.abs(rows[kind].bounds.x-rows[kind].pixelBounds.x)<=2,kind+' must respect actual alignment/bearing');
    }
  } finally{await browser.close();}
});
