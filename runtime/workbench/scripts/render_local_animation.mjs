// Shared deterministic HTML -> frames -> H.264/AAC runner. Artwork remains episode-owned.
import {chromium, browserLaunchOptions} from './playwright_runtime.mjs';
import {createServer} from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn, execFileSync} from 'node:child_process';
import {once} from 'node:events';
const config = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
const project = path.resolve(config.project_root);
const target = path.resolve(config.output);
const fps = Number(config.fps || 24), width = Number(config.width || 1280), height = Number(config.height || 720);
if (![fps,width,height].every(Number.isInteger) || fps<1 || fps>60 || width<64 || height<64 || width%2 || height%2) throw Error('帧率或画布尺寸无效（宽高须为偶数）');
const voice = path.resolve(config.audio);
const probe = JSON.parse(execFileSync('ffprobe',['-v','error','-show_format','-show_streams','-of','json',voice],{encoding:'utf8'}));
if (!probe.streams.some(s=>s.codec_type==='audio')) throw Error('旁白没有音频流');
const duration = Number(probe.format.duration);
if (!(duration>0) || !Number.isFinite(duration)) throw Error('旁白时长无效');
try { await fs.access(target); throw Error('目标已存在，请使用新修订输出路径'); } catch(e) { if(e.code!=='ENOENT') throw e; }
await fs.mkdir(path.dirname(target),{recursive:true});
const temp = await fs.mkdtemp(path.join(path.dirname(target),'.render-'));
const entry = config.entry || 'index.html';
const mime = {'.html':'text/html','.js':'text/javascript','.mjs':'text/javascript','.png':'image/png','.svg':'image/svg+xml','.jpg':'image/jpeg','.webp':'image/webp','.css':'text/css','.woff2':'font/woff2'};
const server = createServer(async(req,res)=>{
  try {
    const name = decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    const file = await fs.realpath(path.resolve(project,'.'+name));
    const rel = path.relative(await fs.realpath(project),file);
    if(rel.startsWith('..') || path.isAbsolute(rel)) {res.writeHead(403).end();return;}
    res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');
    res.end(await fs.readFile(file));
  } catch {res.writeHead(404).end();}
});
server.listen(0,'127.0.0.1'); await once(server,'listening');
let browser, encoder;
const errors = [];
try {
  browser = await chromium.launch(browserLaunchOptions);
  const page = await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
  page.on('pageerror',e=>errors.push(e.message));
  page.on('requestfailed',request=>{ if(request.resourceType()!=='media') errors.push(`资源加载失败: ${request.url()}`); });
  page.on('response',response=>{
    if(response.status()>=400 && new URL(response.url()).pathname!=='/favicon.ico') {
      errors.push(`资源 HTTP ${response.status()}: ${response.url()}`);
    }
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/${entry}`,{waitUntil:'networkidle',timeout:30000});
  await page.addStyleTag({content:'button, [role="button"] { visibility: hidden !important; }'});
  await page.evaluate(async()=>{
    await document.fonts.ready;
    await Promise.all([...document.images].map(img=>img.decode()));
    if(window.__ready) await window.__ready;
    if(typeof window.__seek!=='function') throw Error('动画必须提供 window.__seek(t)');
  });
  const args=['-v','error','-f','image2pipe','-vcodec','png','-framerate',String(fps),'-i','pipe:0','-i',voice,'-map','0:v','-map','1:a','-t',String(duration),'-c:v','libx264','-crf','18','-preset','medium','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-movflags','+faststart',path.join(temp,'video.mp4')];
  encoder = spawn('ffmpeg',args,{stdio:['pipe','ignore','pipe']});
  let fferror=''; encoder.stderr.on('data',chunk=>{fferror=(fferror+chunk).slice(-4000);});
  const done=once(encoder,'close');
  // Catch stream errors through once(drain) / process exit without uncaught EPIPE.
  let pipeError; encoder.stdin.on('error',e=>{pipeError=e;});
  const frames=Math.ceil(duration*fps);
  for(let frame=0;frame<frames;frame++) {
    await page.evaluate(t=>window.__seek(t),frame/fps);
    if(errors.length) throw Error(errors.join('\n'));
    const png=await page.locator('#film').screenshot({type:'png'});
    if(pipeError || encoder.exitCode!==null) throw Error(fferror||String(pipeError||'编码提前结束'));
    if(!encoder.stdin.write(png)) await once(encoder.stdin,'drain');
    if(frame===0 || frame===Math.floor(frames/2) || frame===frames-1) await fs.writeFile(path.join(temp,`frame-${frame}.png`),png);
  }
  encoder.stdin.end();
  const [code] = await done;
  if(code!==0) throw Error(fferror||'FFmpeg 编码失败');
  execFileSync('ffmpeg',['-v','error','-i',path.join(temp,'video.mp4'),'-f','null','-']);
  // Hard-link publishes only a completed file and never overwrites another revision.
  await fs.link(path.join(temp,'video.mp4'),target);
  await fs.unlink(path.join(temp,'video.mp4'));
  console.log(JSON.stringify({status:'rendered',output:target,frames,duration,fps,width,height,evidence_directory:temp,release_eligible:false}));
} finally {
  if(encoder && encoder.exitCode===null) encoder.kill();
  if(browser) await browser.close();
  server.close();
}
