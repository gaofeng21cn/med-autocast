// Technical two-second Canvas -> PNG -> FFmpeg check; no medical content or approval.
import {chromium, browserLaunchOptions} from './playwright_runtime.mjs';
import fs from 'node:fs/promises';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
const base = path.resolve(process.argv[2] || 'outputs');
await fs.mkdir(base, {recursive:true});
const out = await fs.mkdtemp(path.join(base, 'environment-smoke-'));
let browser;
try {
  browser = await chromium.launch(browserLaunchOptions);
  const page = await browser.newPage({viewport:{width:640,height:360}, deviceScaleFactor:1});
  await page.setContent(`<canvas width="640" height="360"></canvas><style>body{margin:0}</style><script>
    const c=document.querySelector('canvas').getContext('2d');
    window.__seek=t=>{c.fillStyle='#efe7d3';c.fillRect(0,0,640,360);c.save();c.translate(100+t*170,180+Math.sin(t*3)*35);c.rotate(t*.4);c.fillStyle='#3c716a';c.beginPath();c.moveTo(-42,-35);c.lineTo(40,-37);c.lineTo(45,32);c.lineTo(-40,37);c.closePath();c.fill();c.strokeStyle='#343734';c.lineWidth=3;c.stroke();c.restore();};
  </script>`);
  for(let frame=0;frame<24;frame++) {
    await page.evaluate(t=>window.__seek(t), frame/12);
    await page.screenshot({path:path.join(out,`${String(frame).padStart(4,'0')}.png`)});
  }
  execFileSync('ffmpeg',['-v','error','-framerate','12','-i',path.join(out,'%04d.png'),'-f','lavfi','-i','anullsrc=r=24000:cl=mono','-t','2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',path.join(out,'smoke.mp4')]);
  const metadata=JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',path.join(out,'smoke.mp4')],{encoding:'utf8'}));
  execFileSync('ffmpeg',['-v','error','-i',path.join(out,'smoke.mp4'),'-f','null','-']);
  const receipt={status:'passed',purpose:'local_environment_only',output:path.join(out,'smoke.mp4'),duration:metadata.format.duration,streams:metadata.streams.map(s=>s.codec_type),production_ready:false,tts_verified:false};
  await fs.writeFile(path.join(out,'receipt.json'),JSON.stringify(receipt,null,2));
  console.log(JSON.stringify(receipt));
} finally {if(browser) await browser.close();}
