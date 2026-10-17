import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const templateRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// Installed portable templates may use a workspace-provided browser runtime.
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
    const require = createRequire(path.join(root, "package.json"));
    try {
      return require(name);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "MODULE_NOT_FOUND") throw error;
    }
  }
  return undefined;
}

const fixtureSource = `
import { Stage } from "./src/kit/stage.ts";
import { paperPlate, paperFood } from "./src/kit/tableware.ts";
import { paperRoom } from "./src/kit/rooms.ts";
import { contactShadow } from "./src/kit/patterns.ts";
import { turnPage } from "./src/kit/actions.ts";

export const fixtures = ['plate','rice','protein','fruit','noodle','room-consult','room-ward','shadow','turnPage'];
export function draw(canvas, fixture, opacity, time = 1.3) {
  const g = canvas.getContext('2d', {willReadFrequently:true});
  const stage = new Stage(g, canvas.width, canvas.height);
  stage.reset();
  g.clearRect(0, 0, canvas.width, canvas.height);
  const state = () => ({
    alpha:g.globalAlpha, fill:g.fillStyle, stroke:g.strokeStyle,
    lineWidth:g.lineWidth, shadowColor:g.shadowColor, shadowBlur:g.shadowBlur,
    shadowOffsetX:g.shadowOffsetX, shadowOffsetY:g.shadowOffsetY,
    transform:Array.from(g.getTransform().toFloat64Array())
  });
  const before = state();
  const alphas = [], originals = {};
  for (const name of ['stroke','fill','fillRect','strokeRect','drawImage','fillText','strokeText']) {
    originals[name] = g[name];
    g[name] = function(...args) {
      alphas.push(g.globalAlpha);
      return originals[name].apply(g, args);
    };
  }
  try {
    stage.group({x:0, y:0, opacity}, () => {
      if (fixture === 'plate') paperPlate(stage, 320, 240, 260);
      else if (['rice','protein','fruit','noodle'].includes(fixture)) paperFood(stage, fixture, {x:320,y:240}, 260);
      else if (fixture.startsWith('room-')) paperRoom(stage, fixture.slice(5));
      else if (fixture === 'shadow') contactShadow(stage, 320, 240, .8, 100);
      else if (fixture === 'turnPage') turnPage(stage, time, {start:.5,end:2.5,x:320,y:240,w:280,h:180});
      else throw Error(fixture);
    });
    const rgba = g.getImageData(0, 0, canvas.width, canvas.height).data;
    let visiblePixels = 0;
    for (let i=3; i<rgba.length; i+=4) if (rgba[i]) visiblePixels++;
    return {rgba, visiblePixels, maxDrawAlpha:Math.max(0,...alphas), restored:JSON.stringify(before) === JSON.stringify(state())};
  } finally {
    for (const name of Object.keys(originals)) g[name] = originals[name];
  }
}
`;

test("paper components inherit parent opacity and render deterministic seeks", { timeout: 120_000 }, async (t) => {
  const playwright = resolveRuntime("playwright");
  const esbuild = resolveRuntime("esbuild");
  if (!playwright || !esbuild) {
    t.skip("未运行像素验证：缺少 Playwright/esbuild；安装模板依赖并设置 MED_AUTOCAST_PLAYWRIGHT_ROOT 或 MED_AUTOCAST_WORKSPACE_ROOT 后重跑。");
    return;
  }
  const built = await esbuild.build({
    stdin: {contents:fixtureSource, resolveDir:templateRoot, loader:"ts"},
    bundle:true, write:false, format:"iife", globalName:"OpacityFixture", target:"es2022",
  });
  const browser = await playwright.chromium.launch({
    headless:true,
    ...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {}),
  });
  try {
    const page = await browser.newPage();
    await page.route("**/*", (route: { abort: () => Promise<void> }) => route.abort());
    await page.setContent("<!doctype html><meta charset=utf-8><title>离线透明度回归</title>");
    await page.addScriptTag({content:built.outputFiles[0].text});
    const results = await page.evaluate(() => {
      const api = (window as any).OpacityFixture;
      const rows = [];
      for (const name of api.fixtures) {
        const canvas = document.createElement("canvas");
        canvas.width = 640;
        canvas.height = 480;
        const hidden = api.draw(canvas, name, 0);
        const partial = api.draw(canvas, name, .3);
        const opaque = api.draw(canvas, name, 1);
        const first = api.draw(canvas, name, .3, 1.3);
        for (const time of [2.7, .2, 2.1, .7]) api.draw(canvas, name, .3, time);
        const sought = api.draw(canvas, name, .3, 1.3);
        rows.push({
          name, hiddenPixels:hidden.visiblePixels,
          partialPixels:partial.visiblePixels, partialDrawAlpha:partial.maxDrawAlpha,
          opaquePixels:opaque.visiblePixels, opaqueDrawAlpha:opaque.maxDrawAlpha,
          restored:[hidden,partial,opaque,first,sought].every(v => v.restored),
          sameSeek:first.rgba.every((v:number, i:number) => v === sought.rgba[i]),
        });
      }
      return rows;
    });
    for (const row of results) {
      await t.test(row.name, () => {
        assert.equal(row.hiddenPixels, 0, "parent opacity=0 must leave no pixels");
        assert.ok(row.partialPixels > 0 && row.opaquePixels > 0, "visible paper must still draw");
        // Overlapping paper layers composite normally; individual draw calls
        // must inherit alpha, not clamp the final composited image to .3.
        assert.ok(row.partialDrawAlpha <= .3 + 1e-8, JSON.stringify(row));
        assert.ok(row.opaqueDrawAlpha <= 1, JSON.stringify(row));
        assert.equal(row.restored, true, "drawing must restore the caller's context");
        assert.equal(row.sameSeek, true, "random seeks must produce identical pixels");
      });
    }
  } finally {
    await browser.close();
  }
});
