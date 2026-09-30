import { Stage } from "./stage";
import { brandMark, caption } from "./overlays";
import { clamp } from "./motion";
import type { Asset, Brand, Score, Shot, ShotContext } from "./types";
export function mount(config: {
  assets: Asset[];
  score: Score;
  shots: Shot[];
  brand?: Brand;
}) {
  const canvas = document.querySelector<HTMLCanvasElement>("#film")!,
    s = new Stage(canvas.getContext("2d")!, canvas.width, canvas.height),
    score = config.score;
  const clean = new URLSearchParams(location.search).has("clean");
  const controls = document.querySelector<HTMLElement>("nav")!,
    audio = document.querySelector<HTMLAudioElement>("#voice"),
    play = document.querySelector<HTMLButtonElement>("#play")!,
    seek = document.querySelector<HTMLInputElement>("#seek")!;
  const chooser = document.createElement("select");
  chooser.setAttribute("aria-label", "选择镜头");
  chooser.innerHTML =
    '<option value="all">整片</option>' +
    score.shots
      .map((b) => `<option value="${b.id}">${b.title}</option>`)
      .join("");
  controls.append(chooser);
  const speed = document.createElement("select");
  speed.setAttribute("aria-label", "播放速度");
  speed.innerHTML =
    '<option value="1">正常速度</option><option value="0.5">半速审片</option>';
  controls.append(speed);
  const loop = document.createElement("input");
  loop.type = "checkbox";
  loop.id = "loop";
  const loopLabel = document.createElement("label");
  loopLabel.append(loop, document.createTextNode("循环"));
  controls.append(loopLabel);
  const cleanLink = document.createElement("a");
  cleanLink.href = clean ? "index.html" : "index.html?clean=1";
  cleanLink.textContent = clean ? "显示字幕" : "去文字审片";
  controls.append(cleanLink);
  const clock = document.createElement("output");
  controls.append(clock);
  let current = 0,
    running = false,
    previous = 0;
  const range = () => {
    const b = score.shots.find((b) => b.id === chooser.value);
    return b ? [b.start, b.end] : [0, score.duration];
  };
  function draw(time: number) {
    current = clamp(time, 0, score.duration - 1e-6);
    const i = Math.max(
      0,
      score.shots.findIndex((b) => current >= b.start && current < b.end),
    );
    const beat = score.shots[i],
      shot = config.shots.find((s) => s.id === beat.id);
    if (!shot) throw Error(`缺少镜头 ${beat.id}`);
    s.reset();
    s.background();
    const ctx: ShotContext = {
      stage: s,
      t: current - beat.start,
      globalTime: current,
      beat,
      clean,
    };
    const camera = shot.camera?.(ctx) || {
      x: s.width / 2,
      y: s.height * 0.42,
      zoom: 1,
    };
    s.camera(camera, () => shot.render(ctx));
    s.tracking = false;
    if (config.brand) brandMark(s, config.brand);
    if (!clean) caption(s, score, current);
    s.tracking = true;
    window.__layout = {
      ...s.layout(),
      subtitle: { x: 70, y: s.height - 105, w: s.width - 140, h: 78 },
    };
    window.__state = {
      scene: i + 1,
      time: current,
      localTime: ctx.t,
      shot: beat.id,
      progress: ctx.t / (beat.end - beat.start),
      events: beat.events,
    };
    seek.value = String(current / score.duration);
    clock.textContent = `${current.toFixed(2)} / ${score.duration.toFixed(2)} 秒`;
  }
  window.__seek = draw;
  window.__cuts = [...score.shots.map((s) => s.start), score.duration];
  window.__total = score.duration;
  window.__score = score;
  window.__kitVersion = "1.1.0";
  window.__rendererId = "canvas2d";
  window.__requestedStyleId = score.style?.styleId;
  window.__styleId = score.style?.appliedStyleId;
  controls.inert = true;
  const ready = (window.__ready = s.load(config.assets).then(async () => {
    await document.fonts.ready;
    draw(0);
    controls.inert = false;
  }));
  const pause = () => {
    running = false;
    audio?.pause();
    play.textContent = "播放";
  };
  play.onclick = async () => {
    await ready;
    if (running) {
      pause();
      return;
    }
    const [start, end] = range();
    if (current < start || current >= end - 1 / score.fps) draw(start);
    if (audio) {
      audio.currentTime = current;
      audio.playbackRate = Number(speed.value);
      await audio.play();
    }
    running = true;
    previous = performance.now();
    play.textContent = "暂停";
  };
  seek.oninput = () => {
    draw(Number(seek.value) * score.duration);
    if (audio) audio.currentTime = current;
  };
  chooser.onchange = () => {
    pause();
    draw(range()[0]);
    if (audio) audio.currentTime = current;
  };
  speed.onchange = () => {
    if (audio) audio.playbackRate = Number(speed.value);
  };
  for (const [name, delta] of [
    ["上一帧", -1],
    ["下一帧", 1],
  ] as const) {
    const b = document.createElement("button");
    b.textContent = name;
    b.onclick = () => {
      pause();
      draw(current + delta / score.fps);
      if (audio) audio.currentTime = current;
    };
    controls.append(b);
  }
  if (audio)
    audio.onended = () => {
      if (!loop.checked) pause();
    };
  function tick(now: number) {
    if (running) {
      const [start, end] = range();
      let next = audio
        ? audio.currentTime
        : current + ((now - previous) / 1000) * Number(speed.value);
      if (next >= end - 1 / score.fps) {
        if (loop.checked) {
          next = start;
          if (audio) {
            audio.currentTime = start;
            void audio.play();
          }
        } else {
          next = end - 1 / score.fps;
          pause();
        }
      }
      draw(next);
    }
    previous = now;
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
  return { stage: s, ready, draw };
}
