// Inspect the exact seekable artwork before committing to a full MP4 render.
import {chromium, browserLaunchOptions} from './playwright_runtime.mjs';
import {createServer} from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {once} from 'node:events';
import {observeLayout,observeCues} from './layout_observations.mjs';
import {captureFilm} from './capture_frame.mjs';
import {collectRuntimeReceipt} from './runtime_receipt.mjs';

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
  const entryUrl=`http://127.0.0.1:${server.address().port}/${entry}`;
  const primaryView=new URL(entryUrl).searchParams.get('clean')==='1'?'clean':'final';
  const cleanAddress=new URL(entryUrl);cleanAddress.searchParams.set('clean','1');
  const cleanUrl=cleanAddress.href;
  const timeline = await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map(image => image.decode()));
    if (window.__ready) await window.__ready;
    if (typeof window.__seek !== 'function' || !(window.__total > 0)) throw Error('预览需要 window.__seek(t) 和 window.__total');
    return {
      duration:window.__total,
      cuts:window.__cuts || [0, window.__total],
      cues:window.__score?.cues || [],
      shots:window.__score?.shots || [],
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
    const state = await page.evaluate(time => { window.__seek(time); return {
      state:window.__state || null, layout:window.__layout || null,
      renderer_id:window.__rendererId || null, style_id:window.__styleId || null,
      declared_texts:(()=>{ try { return typeof window.TEXTS==='function' ? window.TEXTS(time) : null; } catch(error) { return {status:'unavailable',error:String(error)}; } })(),
    }; }, point.time);
    const filename = `${String(index).padStart(3,'0')}-s${point.scene}-${point.time.toFixed(2)}.png`;
    await captureFilm(page,width,height,path.join(output,filename));
    const overlaps = [];
    const layout = state.layout;
    if (layout?.subtitle && Array.isArray(layout.subjects)) {
      const a = layout.subtitle;
      for (const b of layout.subjects) if (a.x < b.x+b.w && a.x+a.w > b.x && a.y < b.y+b.h && a.y+a.h > b.y) overlaps.push(b.name || 'subject');
    }
    frames.push({...point, file:filename, ...state, subtitleOverlaps:overlaps,
      layout_findings:observeLayout(layout,width,height)});
  }
  // Richness debt: the same frame is captured without captions and short labels.
  // If a clean frame carries almost no subject area, the shot is carrying its
  // meaning with type or decoration rather than with paper objects and action.
  // This is evidence for visual-review, never a render gate.
  const richness=[];
  for (const frame of frames) {
    await page.goto(cleanUrl, {waitUntil:'load'});
    await page.waitForFunction(()=>!!window.__ready,null,{timeout:20000});
    await page.addStyleTag({content:'button, [role="button"] { visibility: hidden !important; }'});
    await page.evaluate(time => window.__seek(time), frame.time);
    const cleanFile=`clean-${frame.file}`;
    await captureFilm(page,width,height,path.join(output,cleanFile));
    const cleanState = await page.evaluate(()=>window.__layout||null);
    const subjects = Array.isArray(cleanState?.subjects) ? cleanState.subjects : [];
    const canvasArea = width*height;
    const subjectArea = subjects.reduce((sum,r)=>sum+Math.max(0,r.w)*Math.max(0,r.h),0);
    const cover = canvasArea ? subjectArea/canvasArea : 0;
    const largest = subjects.reduce((best,r)=>Math.max(best,Math.max(0,r.w)*Math.max(0,r.h)),0);
    richness.push({
      scene:frame.scene, time:frame.time, clean_file:cleanFile,
      subject_count:subjects.length,
      subject_coverage:Number(cover.toFixed(4)),
      largest_subject_ratio:canvasArea?Number((largest/canvasArea).toFixed(4)):0,
      subject_names:subjects.map(s=>s.name||'subject'),
    });
  }
  await page.goto(entryUrl,{waitUntil:'load'});
  await page.waitForFunction(()=>!!window.__ready,null,{timeout:20000});
  await page.addStyleTag({content:'button, [role="button"] { visibility: hidden !important; }'});
  const motionStrips=[];
  for (let index=0;index<cuts.length-1;index++) {
    const start=cuts[index],end=cuts[index+1],span=end-start,files=[];
    for (let pose=0;pose<12;pose++) {
      const time=Math.min(timeline.duration-1/30,start+span*(pose+.25)/12);
      await page.evaluate(t=>window.__seek(t),time);
      const filename=`strip-s${index+1}-${String(pose).padStart(2,'0')}.png`;
      await captureFilm(page,width,height,path.join(output,filename));
      files.push(filename);
    }
    const sheet=`strip-s${index+1}.jpg`;
    execFileSync('ffmpeg',['-y','-loglevel','error','-pattern_type','glob','-i',path.join(output,`strip-s${index+1}-*.png`),'-vf','scale=400:-1,tile=4x3:padding=8:margin=8:color=white','-frames:v','1',path.join(output,sheet)]);
    motionStrips.push({scene:index+1,from:start,to:end,frames:files,sheet});
  }
  // Subsecond flashes, contact and release can fall between uniform strip poses.
  // Event images are inspection evidence, never semantic approval or a new gate.
  const eventFrames=[];
  for (const shot of timeline.shots) {
   if(!Number.isFinite(shot.start)||!Number.isFinite(shot.end)||shot.end<=shot.start) continue;
   for (const [event,local] of Object.entries(shot.events || {})) {
    if (!Number.isFinite(local)) continue;
    const at=shot.start+local;
    if(at<rangeStart || at>=rangeEnd) continue;
    for(const [phase,offset] of [['before',-.10],['at',0],['after',.12]]) {
      const time=Math.max(shot.start,Math.min(shot.end-1/30,at+offset));
      if(time<rangeStart || time>=rangeEnd) continue;
      await page.evaluate(t=>window.__seek(t),time);
      const name=`event-${String(shot.id).replace(/[^\p{L}\p{N}_-]/gu,'_')}-${String(event).replace(/[^\p{L}\p{N}_-]/gu,'_')}-${phase}.png`;
      await captureFilm(page,width,height,path.join(output,name));
      eventFrames.push({shot:shot.id,event,phase,time,file:name});
    }
   }
  }
  const randomAccessChecks=[];
  for (let scene=1;scene<cuts.length;scene++) {
    const first = frames.filter(f=>f.scene===scene)[3];
    if (!first) continue;
    await page.evaluate(time => window.__seek(time), first.time);
    const sequential = await captureFilm(page,width,height);
    await page.evaluate(time => window.__seek(time), timeline.duration-1/30);
    await page.evaluate(time => window.__seek(time), 0);
    await page.evaluate(time => window.__seek(time), first.time);
    const randomAccess = await captureFilm(page,width,height);
    const passed=sequential.equals(randomAccess);
    randomAccessChecks.push({scene,time:first.time,passed});
    if (!passed) errors.push(`乱序 seek 不确定: ${first.time.toFixed(3)}s`);
  }
  // Output folders retain earlier inspection evidence. Only this run's frames
  // may enter its contact sheet; a glob would silently include stale times.
  const contactInputs = path.join(output,'contact-frames.ffconcat');
  await fs.writeFile(contactInputs, 'ffconcat version 1.0\n' + frames.map(frame => `file '${frame.file}'\n`).join(''));
  execFileSync('ffmpeg', ['-y','-loglevel','error','-f','concat','-safe','1','-i',contactInputs,'-vf',`scale=400:-1,tile=5x${Math.ceil(frames.length/5)}:padding=8:margin=8:color=white`,'-frames:v','1',path.join(output,'contact.jpg')]);
  const runtimeReceipt = await collectRuntimeReceipt({
    project,
    entry,
    config: { width, height },
  });
  const report = {status:errors.length ? 'failed' : 'previewed', project, output, duration:timeline.duration, range:[rangeStart,rangeEnd], scenes:cuts.length-1, frames, motionStrips, eventFrames, errors, renderer_runtime:timeline.renderer_runtime, runtime_receipt:runtimeReceipt, contact_sheet:path.join(output,'contact.jpg'), release_eligible:false};
  report.text_observations=observeCues({cues:timeline.cues});
  report.primary_view=primaryView;
  report.primary_entry=entry;
  report.quality_debt=frames.flatMap(f=>f.layout_findings.map(d=>({...d,time:f.time,scene:f.scene,owner_stage:'visual-review'})));
  if(primaryView==='clean')report.quality_debt.push({code:'final_text_view_not_sampled',
    owner_stage:'visual-review',blocks_stage_progress:false,
    detail:'本次主视图为去文字；不能据此判断正式画面的标签、字幕与遮挡，请另导出普通预览。'});
  report.richness=richness;
  report.richness_debt=richness.filter(r=>r.subject_count===0||r.subject_coverage<0.06).map(r=>({
    detail:r.subject_count===0?'去文字画面没有登记主体，表达可能只靠文字或装饰':'去文字画面主体占比偏低',
    scene:r.scene, time:r.time, owner_stage:'visual-review', evidence_ref:r.clean_file,
    subject_count:r.subject_count, subject_coverage:r.subject_coverage,
    action:'回到导演重做观看事件；模块不提供构图处方',
  }));
  report.semantic_quality_approved=false;
  report.random_access_checks=randomAccessChecks;
  await fs.writeFile(path.join(output,'preview.json'), JSON.stringify(report,null,2));
  console.log(JSON.stringify({status:report.status, output, frames:frames.length, errors, contact_sheet:report.contact_sheet}));
  if (errors.length) process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  server.close();
}
