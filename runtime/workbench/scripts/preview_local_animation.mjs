// Inspect the exact seekable artwork before committing to a full MP4 render.
import {chromium, browserLaunchOptions} from './playwright_runtime.mjs';
import {createServer} from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {execFileSync} from 'node:child_process';
import {once} from 'node:events';
import {observeLayout,observeCues} from './layout_observations.mjs';
import {captureFilm} from './capture_frame.mjs';
import {collectRuntimeReceipt} from './runtime_receipt.mjs';

async function captureLosslessFrame(page,width,height,pngPath,webpPath) {
  await captureFilm(page,width,height,pngPath);
  execFileSync('cwebp',['-quiet','-lossless','-z','4','-mt',pngPath,'-o',webpPath]);
  await fs.rm(pngPath,{force:true});
}

const config = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
config.compact_motion_strips ??= true;
config.compact_numbered_frames ??= config.compact_motion_strips;
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
let temporaryMotionFrames;
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
    const faces = [...document.fonts].map(f => ({
      family: String(f.family || '').replace(/^["']|["']$/g, ''),
      weight: String(f.weight || 'normal'),
      style: String(f.style || 'normal'),
      status: f.status,
    }));
    return {
      duration:window.__total,
      fps:Number(window.__fps || window.__score?.fps || 24),
      cuts:window.__cuts || [0, window.__total],
      cues:window.__score?.cues || [],
      shots:window.__score?.shots || [],
      fonts: {
        loaded_count: faces.filter(f => f.status === 'loaded').length,
        failed_count: faces.filter(f => f.status === 'error').length,
        loaded_families: [...new Set(faces.filter(f => f.status === 'loaded').map(f => f.family))],
        failed_faces: faces.filter(f => f.status === 'error'),
      },
      renderer_runtime: {
        renderer_id: window.__rendererId || null,
        requested_style_id: window.__requestedStyleId || window.__score?.style?.styleId || null,
        style_id: window.__styleId || null,
      },
    };
  });
  const fps = Math.max(1, Number(config.fps || timeline.fps || 24));
  const frameStep = 1 / fps;
  const rangeStart = Number(config.start ?? 0), rangeEnd = Number(config.end ?? timeline.duration);
  if (!(0 <= rangeStart && rangeStart < rangeEnd && rangeEnd <= timeline.duration)) throw Error('预览窗口无效');
  const cuts = [rangeStart, ...new Set(timeline.cuts.filter(t => Number.isFinite(t) && t > rangeStart && t < rangeEnd)), rangeEnd].sort((a,b)=>a-b);
  const points = [];
  for (let index = 0; index < cuts.length - 1; index++) {
    const start = cuts[index], end = cuts[index + 1], span = end - start;
    for (const fraction of [0, .04, .25, .5, .75, .96]) points.push({scene:index+1, fraction, time:Math.min(timeline.duration-1/30,start+span*fraction)});
  }
  await fs.mkdir(output, {recursive:true});
  temporaryMotionFrames = await fs.mkdtemp(path.join(os.tmpdir(), 'med-preview-frame-'));
  const frames = [];
  const contactSourceFiles = [];
  const mobileSourceFiles = [];
  let posterCanvasRgbRange = null;
  for (const [index, point] of points.entries()) {
    const state = await page.evaluate(({time, samplePoster}) => { window.__seek(time);
      let canvasRgbRange = null;
      if (samplePoster) {
        try {
          const canvas = document.querySelector('#film') || document.querySelector('canvas');
          const ctx = canvas?.getContext?.('2d');
          if (canvas && ctx && canvas.width > 0 && canvas.height > 0) {
            let minR = 255, maxR = 0, minG = 255, maxG = 0, minB = 255, maxB = 0;
            for (let gy = 0; gy < 6; gy++) {
              const py = Math.min(canvas.height - 1, Math.floor(((gy + 0.5) * canvas.height) / 6));
              for (let gx = 0; gx < 8; gx++) {
                const px = Math.min(canvas.width - 1, Math.floor(((gx + 0.5) * canvas.width) / 8));
                const d = ctx.getImageData(px, py, 1, 1).data;
                if (d[0] < minR) minR = d[0]; if (d[0] > maxR) maxR = d[0];
                if (d[1] < minG) minG = d[1]; if (d[1] > maxG) maxG = d[1];
                if (d[2] < minB) minB = d[2]; if (d[2] > maxB) maxB = d[2];
              }
            }
            canvasRgbRange = Math.max(maxR - minR, maxG - minG, maxB - minB);
          }
        } catch { canvasRgbRange = null; }
      }
      return {
      state:window.__state || null, layout:window.__layout || null,
      renderer_id:window.__rendererId || null, style_id:window.__styleId || null,
      canvas_rgb_range: canvasRgbRange,
      declared_texts:(()=>{ try { return typeof window.TEXTS==='function' ? window.TEXTS(time) : null; } catch(error) { return {status:'unavailable',error:String(error)}; } })(),
    }; }, {time: point.time, samplePoster: index === 0 && rangeStart === 0});
    if (index === 0 && rangeStart === 0) posterCanvasRgbRange = state.canvas_rgb_range;
    delete state.canvas_rgb_range;
    const stem = `${String(index).padStart(3,'0')}-s${point.scene}-${point.time.toFixed(2)}`;
    const filename = `${stem}.webp`;
    const scratchPng = path.join(temporaryMotionFrames, `${stem}.png`);
    await captureFilm(page, width, height, scratchPng);
    contactSourceFiles.push(scratchPng);
    if (point.fraction === 0.5) mobileSourceFiles.push(scratchPng);
    const overlaps = [];
    const layout = state.layout;
    if (layout?.subtitle && Array.isArray(layout.subjects)) {
      const a = layout.subtitle;
      for (const b of layout.subjects) if (a.x < b.x+b.w && a.x+a.w > b.x && a.y < b.y+b.h && a.y+a.h > b.y) overlaps.push(b.name || 'subject');
    }
    const layoutFindings = observeLayout(layout, width, height);
    const retainFrame = !config.compact_numbered_frames || overlaps.length > 0 || layoutFindings.length > 0;
    if (retainFrame) {
      execFileSync('cwebp', ['-quiet', '-lossless', '-z', '4', '-mt', scratchPng, '-o', path.join(output, filename)]);
    }
    frames.push({...point, file:filename, ...(retainFrame ? {} : {file_state:'omitted_in_compact_mode'}), ...state, subtitleOverlaps:overlaps,
      layout_findings:layoutFindings});
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
    const cleanStem=`clean-${path.parse(frame.file).name}`;
    const cleanFile=`${cleanStem}.webp`;
    await captureLosslessFrame(
      page,width,height,
      path.join(temporaryMotionFrames,`${cleanStem}.png`),
      path.join(output,cleanFile),
    );
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
  const motionProfiles=[];
  // Normal-size diagnostic frames use lossless WebP. The 12 source poses for
  // each contact strip always stay in an isolated scratch directory; compact
  // mode omits their individual copies after the strip sheet is built.
  for (let index=0;index<cuts.length-1;index++) {
    const start=cuts[index],end=cuts[index+1],span=end-start,files=[],sampleTimes=[],stateTrace=[];
    let prevBuf = null, prevStateKey = null;
    let changedIntervals = 0, stateChangedIntervals = 0, lastChangePose = 0;
    for (let pose=0;pose<12;pose++) {
      const time=Math.min(timeline.duration-1/30,start+span*(pose+.25)/12);
      const runtimeState=await page.evaluate(t=>{window.__seek(t);return window.__state||null;},time);
      const traceEntry = {time,shot:runtimeState?.shot||null,performance:runtimeState?.performance||[]};
      stateTrace.push(traceEntry);
      const stem=`strip-s${index+1}-${String(pose).padStart(2,'0')}`;
      const scratch=path.join(temporaryMotionFrames,`${stem}.png`);
      const buf = await captureFilm(page,width,height,scratch);
      const stateKey = JSON.stringify(traceEntry.performance);
      if (prevBuf !== null) {
        if (!buf.equals(prevBuf)) { changedIntervals += 1; lastChangePose = pose; }
        if (stateKey !== prevStateKey) stateChangedIntervals += 1;
      }
      prevBuf = buf;
      prevStateKey = stateKey;
      if (!config.compact_motion_strips) {
        const filename=`${stem}.webp`;
        execFileSync('cwebp',['-quiet','-lossless','-z','4','-mt',scratch,'-o',path.join(output,filename)]);
        files.push(filename);
      }
      sampleTimes.push(time);
    }
    const lastChangeTime = sampleTimes[lastChangePose] ?? start;
    const tailStaticSeconds = Number(Math.max(0, end - lastChangeTime).toFixed(2));
    const activeRatio = Number((changedIntervals / 11).toFixed(3));
    const possibleStaticShot = span >= 3.0 && changedIntervals === 0;
    const possibleDeadTime = !possibleStaticShot && span >= 4.0 && tailStaticSeconds >= 2.8 && activeRatio < 0.55;
    const possibleRushedEnding = !possibleStaticShot && span >= 2.5 && changedIntervals >= 1 && lastChangePose === 11 && tailStaticSeconds < 0.7;
    motionProfiles.push({
      scene: index + 1,
      shot: stateTrace[0]?.shot || null,
      from: Number(start.toFixed(3)),
      to: Number(end.toFixed(3)),
      duration: Number(span.toFixed(3)),
      changed_intervals: changedIntervals,
      total_intervals: 11,
      active_ratio: activeRatio,
      state_changed_intervals: stateChangedIntervals,
      last_change_pose: lastChangePose,
      tail_static_seconds: tailStaticSeconds,
      possible_static_shot: possibleStaticShot,
      possible_dead_time: possibleDeadTime,
      possible_rushed_ending: possibleRushedEnding,
    });
    const sheet=`strip-s${index+1}.jpg`;
    execFileSync('ffmpeg',['-y','-loglevel','error','-start_number','0','-i',path.join(temporaryMotionFrames,`strip-s${index+1}-%02d.png`),'-frames:v','1','-vf','scale=400:-1,tile=4x3:padding=8:margin=8:color=white',path.join(output,sheet)]);
    motionStrips.push({scene:index+1,from:start,to:end,frames:config.compact_motion_strips ? [] : files,
      frames_retained:!config.compact_motion_strips,frame_format:'lossless_webp',sample_times:sampleTimes,sheet,state_trace:stateTrace});
  }
  // Paired cut-boundary frames (N-1 outgoing last frame vs N incoming first frame)
  // catch premature clears, jump cuts, and cover-transition regressions compactly.
  const cutPairs = [];
  const cutPairSourceFiles = [];
  for (let i = 1; i < cuts.length - 1; i++) {
    const cutTime = cuts[i];
    const beforeTime = Math.max(cuts[i - 1], cutTime - frameStep);
    const afterTime = Math.min(timeline.duration - frameStep, cutTime);
    const beforeState = await page.evaluate(t => { window.__seek(t); return { state: window.__state || null, layout: window.__layout || null }; }, beforeTime);
    const beforePng = path.join(temporaryMotionFrames, `cut-${String(i).padStart(2, '0')}-before.png`);
    const beforeBuf = await captureFilm(page, width, height, beforePng);
    const afterState = await page.evaluate(t => { window.__seek(t); return { state: window.__state || null, layout: window.__layout || null }; }, afterTime);
    const afterPng = path.join(temporaryMotionFrames, `cut-${String(i).padStart(2, '0')}-after.png`);
    const afterBuf = await captureFilm(page, width, height, afterPng);
    cutPairSourceFiles.push(beforePng, afterPng);
    cutPairs.push({
      cut_index: i,
      cut_time: Number(cutTime.toFixed(4)),
      outgoing_scene: i,
      incoming_scene: i + 1,
      before_time: Number(beforeTime.toFixed(4)),
      after_time: Number(afterTime.toFixed(4)),
      outgoing_shot: beforeState.state?.shot || null,
      incoming_shot: afterState.state?.shot || null,
      identical_across_cut: beforeBuf.equals(afterBuf),
    });
  }
  let cutPairsSheet = null;
  if (cutPairSourceFiles.length > 0) {
    const cutInputs = path.join(temporaryMotionFrames, 'cut-pairs.ffconcat');
    await fs.writeFile(cutInputs, 'ffconcat version 1.0\n' + cutPairSourceFiles.map(file => `file '${file.replace(/'/g, "'\\''")}'\n`).join(''));
    cutPairsSheet = path.join(output, 'cut-pairs.jpg');
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', cutInputs, '-vf', `scale=480:-1,tile=2x${cutPairs.length}:padding=8:margin=8:color=white`, '-frames:v', '1', cutPairsSheet]);
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
      const stem=`event-${String(shot.id).replace(/[^\p{L}\p{N}_-]/gu,'_')}-${String(event).replace(/[^\p{L}\p{N}_-]/gu,'_')}-${phase}`;
      const name=`${stem}.webp`;
      await captureLosslessFrame(
        page,width,height,
        path.join(temporaryMotionFrames,`${stem}.png`),
        path.join(output,name),
      );
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
  // Build the contact sheet and exact 360px mobile review sheet from this run's
  // temporary full-resolution captures so compact mode leaves zero redundant frames.
  const contactInputs = path.join(temporaryMotionFrames, 'contact-frames.ffconcat');
  await fs.writeFile(contactInputs, 'ffconcat version 1.0\n' + contactSourceFiles.map(file => `file '${file.replace(/'/g, "'\\''")}'\n`).join(''));
  execFileSync('ffmpeg', ['-y','-loglevel','error','-f','concat','-safe','0','-i',contactInputs,'-vf',`scale=400:-1,tile=5x${Math.ceil(frames.length/5)}:padding=8:margin=8:color=white`,'-frames:v','1',path.join(output,'contact.jpg')]);
  let mobileSheet = null;
  if (mobileSourceFiles.length > 0) {
    const mobileInputs = path.join(temporaryMotionFrames, 'mobile-360.ffconcat');
    await fs.writeFile(mobileInputs, 'ffconcat version 1.0\n' + mobileSourceFiles.map(file => `file '${file.replace(/'/g, "'\\''")}'\n`).join(''));
    const mobileCols = mobileSourceFiles.length === 1 ? 1 : 2;
    const mobileRows = Math.ceil(mobileSourceFiles.length / mobileCols);
    mobileSheet = path.join(output, 'mobile-360.jpg');
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', mobileInputs, '-vf', `scale=360:-1,tile=${mobileCols}x${mobileRows}:padding=8:margin=8:color=white`, '-frames:v', '1', mobileSheet]);
  }
  const runtimeReceipt = await collectRuntimeReceipt({
    project,
    entry,
    config: { width, height },
  });
  const posterSubjects = Array.isArray(frames[0]?.layout?.subjects) ? frames[0].layout.subjects.length : 0;
  const midScene1 = frames.find(f => f.scene === 1 && f.fraction === 0.5);
  const midScene1Subjects = Array.isArray(midScene1?.layout?.subjects) ? midScene1.layout.subjects.length : 0;
  const posterFrame = {
    time: frames[0]?.time ?? rangeStart,
    canvas_rgb_range: posterCanvasRgbRange,
    layout_subject_count: posterSubjects,
    mid_scene1_subject_count: midScene1Subjects,
    blank_risk: rangeStart === 0 && (
      (posterCanvasRgbRange !== null && posterCanvasRgbRange < 8) ||
      (posterSubjects === 0 && midScene1Subjects > 0)
    ),
  };
  const report = {
    status:errors.length ? 'failed' : 'previewed', project, output, duration:timeline.duration, fps,
    range:[rangeStart,rangeEnd], scenes:cuts.length-1, frames, motionStrips, motion_profiles:motionProfiles,
    poster_frame:posterFrame, cutPairs, eventFrames, errors, font_observations:timeline.fonts, renderer_runtime:timeline.renderer_runtime,
    runtime_receipt:runtimeReceipt, contact_sheet:path.join(output,'contact.jpg'),
    mobile_sheet:mobileSheet, mobile_review_width_px:360, cut_pairs_sheet:cutPairsSheet, release_eligible:false,
  };
  report.storage_profile={review_frames:'lossless_webp',numbered_frames:config.compact_numbered_frames?'findings_only_contact_preserved':'lossless_webp',motion_strips:'jpeg',motion_strip_source_frames:config.compact_motion_strips?'temporary':'lossless_webp',cut_pairs:'jpeg',mobile_sheet:'jpeg_360px'};
  report.text_observations=observeCues({cues:timeline.cues});
  report.primary_view=primaryView;
  report.primary_entry=entry;
  report.quality_debt=frames.flatMap(f=>f.layout_findings.map(d=>({...d,time:f.time,scene:f.scene,owner_stage:'visual-review'})));
  if (posterFrame.blank_risk) {
    report.quality_debt.push({
      code:'poster_frame_blank_risk', owner_stage:'visual-review', blocks_stage_progress:false,
      scene:1, time:posterFrame.time, canvas_rgb_range:posterFrame.canvas_rgb_range,
      detail:'定位提示：第 0 帧疑似空屏或无主视觉（可能因 fadeIn(0)=0 或开场空等）；首帧应即封面海报，建议直接呈现可辨主体。',
    });
  }
  for (const mp of motionProfiles) {
    if (mp.possible_static_shot) {
      report.quality_debt.push({
        code:'possible_static_shot', owner_stage:'visual-review', blocks_stage_progress:false,
        scene:mp.scene, shot:mp.shot, duration:mp.duration,
        detail:`定位提示：第 ${mp.scene} 镜（${mp.duration}s）在 12 个采样点无像素变化；核对是有意静止读图，还是缺少主体变化/表达发展。`,
      });
    } else if (mp.possible_dead_time) {
      report.quality_debt.push({
        code:'possible_motion_dead_time', owner_stage:'visual-review', blocks_stage_progress:false,
        scene:mp.scene, shot:mp.shot, duration:mp.duration, tail_static_seconds:mp.tail_static_seconds,
        detail:`定位提示：第 ${mp.scene} 镜末尾约 ${mp.tail_static_seconds}s 无视觉变化；核对是否为必要阅读停留，或属于动作结束后的空转等待。`,
      });
    } else if (mp.possible_rushed_ending) {
      report.quality_debt.push({
        code:'possible_rushed_ending', owner_stage:'visual-review', blocks_stage_progress:false,
        scene:mp.scene, shot:mp.shot, duration:mp.duration, tail_static_seconds:mp.tail_static_seconds,
        detail:`定位提示：第 ${mp.scene} 镜末尾不足 0.7s 仍在变化；核对关键结论/数字是否留足 1.0–1.5s 落位读图稳定期，或属于有意持续运镜承接。`,
      });
    }
  }
  if (timeline.fonts?.failed_count > 0) {
    report.quality_debt.push({
      code:'font_load_error', owner_stage:'media-production', blocks_stage_progress:false,
      failed_faces:timeline.fonts.failed_faces,
      detail:'检测到字体加载失败，可能已发生非预期字体回退；先查字体资源再审排版层级。',
    });
  }
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
  if (temporaryMotionFrames) await fs.rm(temporaryMotionFrames, {recursive:true, force:true});
}
