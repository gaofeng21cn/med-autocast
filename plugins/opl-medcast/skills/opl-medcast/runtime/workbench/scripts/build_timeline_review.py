"""Offline filmstrip, PCM waveform, SRT and optional beat-local ASR timing.

Inspired by video-use timeline_view (9575612); independently implemented for
this workbench. Outputs inspection evidence, never approval or edited media.
"""
from __future__ import annotations

import argparse
import array
import html
import io
import json
import math
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from build_episode_video import parse_srt
from workbench_config import resolve_font, series_paths

SCOPE = 'sampled_frames_pcm_waveform_srt_optional_asr; not full motion/listening/medical review'


def run(command):
    return subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))


def words(alignment, beats):
    if not alignment:
        return []
    data = json.loads(alignment.read_text())
    timing = json.loads(beats.read_text())
    if not data.get('episode_id') or data.get('episode_id') != timing.get('episode_id'):
        raise ValueError('ASR and beat timing episode IDs differ')
    origins = {b['id']: float(b['start']) for b in timing['beats']}
    if len(origins) != len(timing['beats']):
        raise ValueError('Duplicate beat IDs')
    result = []
    for beat in data['beats']:
        origin = origins[beat['id']]
        for segment in beat['segments']:
            for word in segment.get('words', []):
                a, b = origin + float(word['start']), origin + float(word['end'])
                if not (math.isfinite(a) and math.isfinite(b) and 0 <= a <= b):
                    raise ValueError('Invalid ASR word time')
                result.append((a, b, word['word']))
    return sorted(result)


def sample_times(start, end, frames, meta):
    video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
    duration = float(video.get('duration') or meta['format']['duration'])
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration):
        raise ValueError(f'Range must satisfy 0 <= start < end <= video duration {duration:.6f}')
    if not 2 <= frames <= 24:
        raise ValueError('frames must be 2..24')
    rate = video.get('avg_frame_rate') or video.get('r_frame_rate')
    fps = float(Fraction(rate))
    if fps <= 0:
        raise ValueError('Video frame rate unavailable')
    # Audio/container duration may extend past video. Never seek exactly EOF.
    last = max(0, duration - 1 / fps)
    a, b = min(start, last), min(end, last)
    return [a + (b - a) * i / (frames - 1) for i in range(frames)]


def wrap(text, font, width):
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for char in paragraph:
            if line and font.getlength(line + char) > width:
                lines.append(line)
                line = ''
            line += char
        lines.append(line)
    return lines


def checked_record(path, duration, srt=None):
    record = json.loads(path.read_text())
    source = srt.resolve() if srt else Path(record['srt_source'])
    if not source.is_absolute():
        source = path.parent / source
    if not source.is_file():
        raise ValueError(f'SRT not found: {source}')
    segments = record.get('segments', [])
    previous = 0.0
    for segment in segments:
        a, b = float(segment['start']), float(segment['end'])
        if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b):
            raise ValueError('Invalid review segment')
        if abs(a - previous) > .05:
            raise ValueError('Review segments have gap/overlap or do not start at zero')
        previous = b
    if previous > duration + .05:
        raise ValueError('Review segments extend beyond video duration')
    return record, source


def protect_outputs(args, outputs):
    inputs = [args.video, args.srt, args.alignment, args.beats, args.review_record, args.font]
    protected = {p.resolve() for p in inputs if p}
    for output in outputs:
        if output.resolve() in protected:
            raise ValueError('Output would overwrite an input')
        if output.exists():
            raise ValueError(f'Output already exists; use a new output path: {output}')


def build(args):
    started = time.perf_counter()
    meta = probe(args.video)
    times = sample_times(args.start, args.end, args.frames, meta)
    if bool(args.alignment) != bool(args.beats):
        raise ValueError('alignment and beats must be supplied together')
    if any(not math.isfinite(t) for t in args.cuts):
        raise ValueError('Cut times must be finite')
    if args.output.suffix.lower() != '.png':
        raise ValueError('Output must end with .png')
    font = ImageFont.truetype(str(args.font), 18)
    small = ImageFont.truetype(str(args.font), 14)
    cols, cellw, cellh, margin = min(4, args.frames), 304, 204, 20
    width = cols * cellw + 2 * margin
    text_width = width - 2 * margin
    cues = [(a, b, t) for a, b, t in parse_srt(args.srt) if b > args.start and a < args.end]
    wt = [w for w in words(args.alignment, args.beats) if w[1] > args.start and w[0] < args.end]
    heading = wrap(f'{args.video.name}  {args.start:.3f}–{args.end:.3f}s · 离线检查', font, text_width)
    note = wrap('SRT为文字依据；ASR仅辅助定位，可能有错。本图不证明完整动态、听感或医学终审。', small, text_width)
    top = 12 + len(heading) * 24 + len(note) * 19 + 8
    timeline_top = top + math.ceil(args.frames / cols) * cellh
    cue_lines = [wrap(t, font, text_width) for _, _, t in cues]
    height = timeline_top + 245 + sum(26 + len(lines) * 25 for lines in cue_lines) + 20
    im = Image.new('RGB', (width, height), '#f6f3ec')
    draw = ImageDraw.Draw(im)
    y = 12
    for line in heading:
        draw.text((margin, y), line, font=font, fill='#203936'); y += 24
    for line in note:
        draw.text((margin, y), line, font=small, fill='#485851'); y += 19
    for i, timestamp in enumerate(times):
        raw = run(['ffmpeg', '-v', 'error', '-ss', str(timestamp), '-i', str(args.video),
                   '-frames:v', '1', '-vf', 'scale=304:176:force_original_aspect_ratio=decrease,pad=304:176:(ow-iw)/2:(oh-ih)/2',
                   '-f', 'image2pipe', '-vcodec', 'png', '-'])
        if not raw:
            raise ValueError(f'No frame at {timestamp}; no previous frame reused')
        frame = Image.open(io.BytesIO(raw)).convert('RGB')
        x, y = margin + i % cols * cellw, top + i // cols * cellh
        im.paste(frame, (x, y))
        draw.text((x + 4, y + 180), f'取帧 {timestamp:.3f}s', font=small, fill='#203936')
    x0, x1 = margin, width - margin

    def x(t):
        return x0 + round((t - args.start) / (args.end - args.start) * (x1 - x0))

    ym = timeline_top + 57
    draw.text((x0, timeline_top), '实际音轨波形（绝对峰值，非听辨）', font=small, fill='#203936')
    draw.line((x0, ym, x1, ym), fill='#bdc5bc')
    audio_present = any(s['codec_type'] == 'audio' for s in meta['streams'])
    if audio_present:
        pcm = array.array('h', run(['ffmpeg', '-v', 'error', '-ss', str(args.start), '-i', str(args.video),
                                   '-t', str(args.end - args.start), '-vn', '-ac', '1', '-ar', '16000', '-f', 's16le', '-']))
        if sys.byteorder != 'little':
            pcm.byteswap()
        if not pcm:
            raise ValueError('Audio stream exists but requested window produced no PCM')
        for col in range(x1 - x0):
            samples = pcm[len(pcm)*col//(x1-x0):len(pcm)*(col+1)//(x1-x0)]
            peak = max((abs(s) for s in samples), default=0) / 32768
            draw.line((x0 + col, ym - peak*38, x0 + col, ym + peak*38), fill='#42857a')
    else:
        draw.text((x0, timeline_top + 22), '此素材无音轨', font=small, fill='#8b4438')
    for i in range(6):
        t = args.start + (args.end - args.start) * i / 5
        draw.text((min(x(t), x1 - 65), ym + 42), f'{t:.2f}s', font=small, fill='#203936')
    for t in args.cuts:
        if args.start <= t <= args.end:
            draw.line((x(t), timeline_top + 19, x(t), ym + 40), fill='#d45b37', width=2)
            label = f'切点 {t:.3f}'
            draw.text((min(x(t)+3, x1-small.getlength(label)), timeline_top+18), label, font=small, fill='#93442f')
    wy = ym + 68
    draw.text((x0, wy), 'ASR词级定位（完整词表见JSON）' if args.alignment else '未提供逐词对齐，仅使用SRT', font=small, fill='#485851')
    lanes = [-100] * 3
    shown = 0
    for a, b, text in wt:
        xx, endx = x(max(a, args.start)), x(min(b, args.end))
        length = small.getlength(text)
        labelx = min(xx, x1-length)
        lane = next((i for i, end in enumerate(lanes) if labelx >= end and labelx >= x0), None)
        if lane is None:
            continue
        yy = wy + 24 + lane*23
        draw.line((xx, yy, max(xx+1, endx), yy), fill='#79969c', width=2)
        draw.text((labelx, yy+1), text, font=small, fill='#485851')
        lanes[lane] = labelx + length + 3
        shown += 1
    if shown < len(wt):
        draw.text((x0, timeline_top+220), f'图中省略{len(wt)-shown}个拥挤标签；完整时码保存在JSON。', font=small, fill='#8b4438')
    cy = timeline_top + 245
    for (a, b, _), lines in zip(cues, cue_lines):
        draw.text((x0, cy), f'{a:.3f}–{b:.3f}  SRT原文', font=small, fill='#4a756e')
        cy += 23
        for line in lines:
            draw.text((x0, cy), line, font=font, fill='#203936'); cy += 25
        cy += 3
    inputs = {name: {'path': str(p.resolve())} for name, p in
              [('video', args.video), ('srt', args.srt), ('alignment', args.alignment), ('beats', args.beats), ('review_record', args.review_record)] if p}
    report = {'schema': 'medical_video_timeline_review/v1', 'video': str(args.video.resolve()),
              'inputs': inputs,
              'range': [args.start, args.end], 'frame_times': times, 'cuts': args.cuts,
              'audio_present': audio_present, 'asr_words': wt, 'asr_word_count': len(wt), 'asr_labels_shown': shown,
              'srt_cues': cues, 'srt_rendered_lines': cue_lines, 'elapsed_seconds': round(time.perf_counter()-started, 3),
              'output': str(args.output.resolve()), 'review_scope': SCOPE, 'review_status': 'pending'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents stale evidence from silently overwriting a prior run.
    with args.output.open('xb') as f:
        im.save(f, format='PNG')
    with args.output.with_suffix('.json').open('x') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series')
    parser.add_argument('--episode')
    parser.add_argument('--video', type=Path)
    parser.add_argument('--srt', type=Path)
    parser.add_argument('--review-record', type=Path, help='Read segments and srt_source from this review JSON; does not inherit approval')
    parser.add_argument('--start', type=float)
    parser.add_argument('--end', type=float)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--all-cuts', action='store_true')
    parser.add_argument('--radius', type=float, default=1.5)
    parser.add_argument('--frames', type=int, default=8)
    parser.add_argument('--alignment', type=Path)
    parser.add_argument('--beats', type=Path)
    parser.add_argument('--cuts', type=float, nargs='*', default=[])
    parser.add_argument('--font', type=Path)
    args = parser.parse_args()
    if bool(args.series) != bool(args.episode):
        parser.error('series and episode must be supplied together')
    if args.series:
        if Path(args.episode).name != args.episode or args.episode in {'.', '..'}:
            parser.error('episode must be a single directory name')
        published = series_paths(args.series)['publish_root'] / args.episode
        args.video = args.video or published / 'video.mp4'
        if not args.review_record and not args.srt:
            args.review_record = published / '审看记录.json'
    if not args.video:
        parser.error('provide video or series + episode')
    record = None
    if args.review_record:
        meta = probe(args.video)
        video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
        duration = float(video.get('duration') or meta['format']['duration'])
        record, args.srt = checked_record(args.review_record, duration, args.srt)
        if args.series and record.get('episode') != args.episode:
            parser.error('review record episode mismatch')
        args.cuts = sorted(set(args.cuts + [float(s['start']) for s in record['segments'][1:]]))
    if not args.srt:
        parser.error('provide srt or a review record with srt_source')
    args.font = resolve_font(args.font)
    if args.all_cuts:
        if args.start is not None or args.end is not None or args.output:
            parser.error('all-cuts uses output-dir, not start/end/output')
        if not args.output_dir or not args.cuts:
            parser.error('all-cuts requires output-dir and actual cuts or review record')
        if not math.isfinite(args.radius) or args.radius <= 0:
            parser.error('radius must be finite and positive')
        meta = probe(args.video)
        video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
        duration = float(video.get('duration') or meta['format']['duration'])
        if any(not math.isfinite(t) or not 0 < t < duration for t in args.cuts):
            parser.error('all cut times must fall inside the video')
        outputs = [args.output_dir / f'cut-{i+1:03}.png' for i in range(len(args.cuts))]
        protect_outputs(args, outputs + [p.with_suffix('.json') for p in outputs] + [args.output_dir/'index.html', args.output_dir/'index.json'])
        reports = []
        for cut, output in zip(args.cuts, outputs):
            args.start, args.end, args.output = max(0, cut-args.radius), min(duration, cut+args.radius), output
            reports.append(build(args))
        index = {'schema': 'medical_video_cut_review_index/v1', 'review_status': 'pending', 'review_scope': SCOPE, 'windows': reports}
        (args.output_dir/'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2))
        entries = ''.join(f'<section><h2>{r["range"][0]:.3f}–{r["range"][1]:.3f}s</h2><a href="{Path(r["output"]).name}"><img src="{Path(r["output"]).name}" alt="切点检查图"></a></section>' for r in reports)
        sources = '<ul>' + ''.join(f'<li>{html.escape(name)}: {html.escape(info["path"])}</li>' for name, info in reports[0]['inputs'].items()) + '</ul>'
        (args.output_dir/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>切点检查</title><style>body{max-width:1260px;margin:24px auto;font-family:sans-serif;background:#f6f3ec}img{width:100%}section{margin:28px 0}</style><h1>切点检查 · 待人工复核</h1><p>'+html.escape(str(args.video.resolve()))+'</p>'+sources+'<p>仅静态图，无播放器或音频。抽帧、波形和字幕不代表完整动态、听感或医学终审。</p>'+entries)
        print(json.dumps({'windows': len(reports), 'elapsed_seconds': round(sum(r['elapsed_seconds'] for r in reports), 3), 'index': str((args.output_dir/'index.html').resolve()), 'review_status':'pending'}, ensure_ascii=False))
    else:
        if args.start is None or args.end is None or not args.output or args.output_dir:
            parser.error('single window requires start, end and output')
        protect_outputs(args, [args.output, args.output.with_suffix('.json')])
        report = build(args)
        print(json.dumps({k: report[k] for k in ['output','range','elapsed_seconds','review_status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
