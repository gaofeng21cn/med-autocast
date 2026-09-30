// Inspect the exact seekable artwork before committing to a full MP4 render.
import {chromium, browserLaunchOptions} from './playwright_runtime.mjs';
import {createServer} from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {once} from 'node:events';

const config = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
const project = path.resolve(config.project_root);
const output = path.resolve(config.output);
const entry = config.entry || 'index.html';
const width = Number(config.width || 1280), height = Number(config.height || 720);
const mime = {'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.png':'image/png','.svg':'image/svg+xml','.jpg':'image/jpeg','.webp':'image/webp','.css':'text/css','.wav':'audio/wav','.mp3':'audio/mpeg'};
const base = await fs.realpath(project);
const server = createServer(async (request, response) => {
  try {
    const name = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
    const file = await fs.realpath(path.resolve(base, '.' + name));
    const relative = path.relative(base, file);
    if (relative.startsWith('..') || path.isAbsolute(relative)) { response.writeHead(403).end(); return; }
    response.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream');
    response.end(await fs.readFile(file));
  } catch { response.writeHead(404).end(); }
});
server.listen(0, '127.0.0.1');
await once(server, 'listening');
let browser;
try {
  browser = await chromium.launch(browserLaunchOptions);
  const page = await browser.newPage({viewport:{width,height}, deviceScaleFactor:1});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('requestfailed', request => {
    // Chromium may cancel an unused <audio> preload; visual preview does not play it.
    if (request.resourceType() !== 'media') errors.push(`资源加载失败: ${request.url()}`);
  });
  page.on('response', response => {
    if (response.status() >= 400 && new URL(response.url()).pathname !== '/favicon.ico') errors.push(`资源 HTTP ${response.status()}: ${response.url()}`);
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/${entry}`, {waitUntil:'networkidle', timeout:30000});
  await page.addStyleTag({content:'button, [role="button"] { visibility: hidden !important; }'});
  const timeline = await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map(image => image.decode()));
    if (window.__ready) await window.__ready;
    if (typeof window.__seek !== 'function' || !(window.__total > 0)) throw Error('预览需要 window.__seek(t) 和 window.__total');
    return {
      duration:window.__total,
      cuts:window.__cuts || [0, window.__total],
      renderer_runtime: {
        renderer_id: window.__rendererId || null,
        requested_style_id: window.__requestedStyleId || window.__score?.style?.styleId || null,
        style_id: window.__styleId || null,
      },
    };
  });
  const rangeStart = Number(config.start ?? 0), rangeEnd = Number(config.end ?? timeline.duration);
  if (!(0 <= rangeStart && rangeStart < rangeEnd && rangeEnd <= timeline.duration)) throw Error('预览窗口无效');
  const cuts = [rangeStart, ...new Set(timeline.cuts.filter(t => Number.isFinite(t) && t > rangeStart && t < rangeEnd)), rangeEnd].sort((a,b)=>a-b);
  const points = [];
  for (let index = 0; index < cuts.length - 1; index++) {
    const start = cuts[index], end = cuts[index + 1], span = end - start;
    for (const fraction of [0, .04, .25, .5, .75, .96]) points.push({scene:index+1, time:Math.min(timeline.duration-1/30,start+span*fraction)});
  }
  await fs.mkdir(output, {recursive:true});
  const frames = [];
  for (const [index, point] of points.entries()) {
    const state = await page.evaluate(time => { window.__seek(time); return {state:window.__state || null, layout:window.__layout || null}; }, point.time);
    const filename = `${String(index).padStart(3,'0')}-s${point.scene}-${point.time.toFixed(2)}.png`;
    await page.locator('#film').screenshot({path:path.join(output,filename)});
    const overlaps = [];
    const layout = state.layout;
    if (layout?.subtitle && Array.isArray(layout.subjects)) {
      const a = layout.subtitle;
      for (const b of layout.subjects) if (a.x < b.x+b.w && a.x+a.w > b.x && a.y < b.y+b.h && a.y+a.h > b.y) overlaps.push(b.name || 'subject');
    }
    frames.push({...point, file:filename, ...state, subtitleOverlaps:overlaps});
  }
  const motionStrips=[];
  for (let index=0;index<cuts.length-1;index++) {
    const start=cuts[index],end=cuts[index+1],span=end-start,files=[];
    for (let pose=0;pose<12;pose++) {
      const time=Math.min(timeline.duration-1/30,start+span*(pose+.25)/12);
      await page.evaluate(t=>window.__seek(t),time);
      const filename=`strip-s${index+1}-${String(pose).padStart(2,'0')}.png`;
      await page.locator('#film').screenshot({path:path.join(output,filename)});
      files.push(filename);
    }
    const sheet=`strip-s${index+1}.jpg`;
    execFileSync('ffmpeg',['-y','-loglevel','error','-pattern_type','glob','-i',path.join(output,`strip-s${index+1}-*.png`),'-vf','scale=400:-1,tile=4x3:padding=8:margin=8:color=white','-frames:v','1',path.join(output,sheet)]);
    motionStrips.push({scene:index+1,from:start,to:end,frames:files,sheet});
  }
  if (frames.length) {
    const first = frames[Math.floor(frames.length/2)];
    await page.evaluate(time => window.__seek(time), first.time);
    const sequential = await page.locator('#film').screenshot();
    await page.evaluate(time => window.__seek(time), 0);
    await page.evaluate(time => window.__seek(time), first.time);
    const randomAccess = await page.locator('#film').screenshot();
    if (!sequential.equals(randomAccess)) errors.push(`乱序 seek 不确定: ${first.time.toFixed(3)}s`);
  }
  execFileSync('ffmpeg', ['-y','-loglevel','error','-pattern_type','glob','-i',path.join(output,'[0-9][0-9][0-9]-*.png'),'-vf',`scale=400:-1,tile=5x${Math.ceil(frames.length/5)}:padding=8:margin=8:color=white`,'-frames:v','1',path.join(output,'contact.jpg')]);
  const report = {status:errors.length ? 'failed' : 'previewed', project, output, duration:timeline.duration, range:[rangeStart,rangeEnd], scenes:cuts.length-1, frames, motionStrips, errors, renderer_runtime:timeline.renderer_runtime, contact_sheet:path.join(output,'contact.jpg'), release_eligible:false};
  await fs.writeFile(path.join(output,'preview.json'), JSON.stringify(report,null,2));
  console.log(JSON.stringify({status:report.status, output, frames:frames.length, errors, contact_sheet:report.contact_sheet}));
  if (errors.length) process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  server.close();
}
