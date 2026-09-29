(() => {
const clamp01 = value => Math.max(0, Math.min(1, value));
const smooth = value => { const x = clamp01(value); return x * x * (3 - 2 * x); };

// Timeline helpers are pure so preview frames and final encoding use identical poses.
const move = (time, start, duration) => smooth((time - start) / duration);
const between = (from, to, progress) => from + (to - from) * progress;
const windowed = (time, enter, leave, duration = .35) =>
  move(time, enter, duration) * (1 - move(time, leave, duration));
window.PaperMotion = {move, between, windowed};
})();
