import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const templateRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
function resolveRuntime(name: string) {
  const roots = [
    process.env.MED_AUTOCAST_WORKSPACE_ROOT,
    process.env.MED_AUTOCAST_PLAYWRIGHT_ROOT,
    process.env.MED_AUTOCAST_WORKSPACE_ROOT
      ? path.join(process.env.MED_AUTOCAST_WORKSPACE_ROOT, "templates/animation/paper_theatre")
      : undefined,
  ];
  for (let root = templateRoot; ; root = path.dirname(root)) {
    roots.push(root);
    if (path.dirname(root) === root) break;
  }
  for (const root of roots) {
    if (!root) continue;
    try {
      return createRequire(path.join(root, "package.json"))(name);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "MODULE_NOT_FOUND") throw error;
    }
  }
  return undefined;
}

test("Canvas captions draw separate lines and bound every visible glyph", { timeout: 120_000 }, async (t) => {
  const playwright = resolveRuntime("playwright"), esbuild = resolveRuntime("esbuild");
  if (!playwright || !esbuild) {
    t.skip("未运行字幕像素验证：缺少 Playwright/esbuild；安装模板依赖并指定 MED_AUTOCAST_WORKSPACE_ROOT 后重跑。");
    return;
  }
  const built = await esbuild.build({
    stdin: {
      contents: `import { Stage } from "./src/kit/stage.ts";
import { caption } from "./src/kit/overlays.ts";
export function draw(text, background, time = 1) {
  const canvas = document.createElement('canvas'); canvas.width=1280; canvas.height=720;
  const g = canvas.getContext('2d', {willReadFrequently:true});
  g.fillStyle=background; g.fillRect(0,0,canvas.width,canvas.height);
  const plain=g.getImageData(0,0,canvas.width,canvas.height).data;
  const state=() => JSON.stringify({font:g.font,alpha:g.globalAlpha,align:g.textAlign,
    baseline:g.textBaseline,fill:g.fillStyle,stroke:g.strokeStyle,width:g.lineWidth,
    join:g.lineJoin,shadow:g.shadowColor});
  const before=state(), calls=[], samples=[];
  const fillText=g.fillText, strokeText=g.strokeText, getImageData=g.getImageData;
  g.fillText=function(text,x,y) {
    calls.push({kind:'fill',text,x,y,font:g.font,color:g.fillStyle});
    return fillText.call(g,text,x,y);
  };
  g.strokeText=function(text,x,y) {
    calls.push({kind:'stroke',text,x,y}); return strokeText.call(g,text,x,y);
  };
  g.getImageData=function(x,y,w,h) {
    samples.push({x,y,w,h}); return getImageData.call(g,x,y,w,h);
  };
  const bounds=caption(new Stage(g,1280,720), {cues:[{start:0,end:2,text}]}, time);
  const restored=state()===before;
  const rgba=getImageData.call(g,0,0,1280,720).data;
  const rows=new Set(); let pixels=0,escaped=0;
  for(let y=0;y<720;y++)for(let x=0;x<1280;x++) {
    const i=(y*1280+x)*4;
    if(rgba[i]===plain[i] && rgba[i+1]===plain[i+1] && rgba[i+2]===plain[i+2])continue;
    rows.add(y); pixels++;
    if(!bounds || x<Math.floor(bounds.x) || x>=Math.ceil(bounds.x+bounds.w) ||
        y<Math.floor(bounds.y) || y>=Math.ceil(bounds.y+bounds.h))escaped++;
  }
  let bands=0, prior=-2;
  for(const y of rows) { if(y!==prior+1)bands++; prior=y; }
  return {bounds,calls,samples,restored,pixels,escaped,bands};
}`,
      resolveDir:templateRoot, loader:"ts",
    },
    bundle:true, write:false, format:"iife", globalName:"CaptionFixture", target:"es2022",
  });
  const browser = await playwright.chromium.launch({
    headless:true, ...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {}),
  });
  try {
    const page = await browser.newPage();
    await page.route("**/*", (route: {abort: () => Promise<void>}) => route.abort());
    await page.setContent("<!doctype html><meta charset=utf-8><title>离线字幕回归</title>");
    await page.addScriptTag({content:built.outputFiles[0].text});
    const results = await page.evaluate(() => {
      const api=(window as any).CaptionFixture, rows=[];
      for(const background of ["#f1e7d0", "#263733"])
        for(const text of ["看字清楚", "看字清楚\n周边视野", "看字清楚\r\n周边视野", "看字清楚\r周边视野"]) {
          const first=api.draw(text,background);
          api.draw(text,background,2.1);
          rows.push({text,background,...first,sameSeek:JSON.stringify(first)===JSON.stringify(api.draw(text,background))});
        }
      return {rows, expired:api.draw("看字清楚", "#f1e7d0", 2)};
    });
    for (const row of results.rows) {
      await t.test(`${row.background} ${JSON.stringify(row.text)}`, () => {
        const lines=row.text.split(/\r\n|\r|\n/);
        const fills=row.calls.filter((c: any) => c.kind === "fill");
        const strokes=row.calls.filter((c: any) => c.kind === "stroke");
        assert.deepEqual(fills.map((c: any) => c.text),lines);
        assert.deepEqual(strokes.map((c: any) => c.text),lines);
        assert.equal(fills.at(-1).y,653, "existing last-line baseline must stay fixed");
        assert.ok(fills.every((c: any, i:number) => c.x === 640 && c.y === 653-(lines.length-1-i)*33));
        assert.ok(fills.every((c: any) => c.font.startsWith("500 27px")));
        assert.ok(fills.every((c: any) => c.color === (row.background === "#263733" ? "#fff8e8" : "#253f3b")));
        assert.equal(row.samples.length,lines.length*5, "sample each line's real background");
        assert.equal(row.bands,lines.length, "real pixels must occupy separate line bands");
        assert.ok(row.pixels > 0);
        assert.equal(row.escaped,0, "returned bounds must include all glyph and stroke pixels");
        assert.ok(row.bounds.y >= 600 && row.bounds.y+row.bounds.h <= 670);
        assert.equal(row.restored,true);
        assert.equal(row.sameSeek,true);
      });
    }
    assert.equal(results.expired.pixels,0);
    assert.equal(results.expired.calls.length,0);
    assert.equal(results.expired.bounds,undefined);
  } finally {
    await browser.close();
  }
});
