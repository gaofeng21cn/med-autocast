#!/usr/bin/env python3
"""复查登记单集的真实预览几何；只定位，不推断文字所属纸件或批准质量。"""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path
from collections import Counter
import yaml

KINDS = {"text_outside_canvas", "text_text_intersection", "text_subtitle_intersection",
         "text_region_overflow", "unbound_text_subject_partial_overlap"}

def audit(workspace: Path, previews: Path, output: Path, overrides: dict[str, Path]):
    config = yaml.safe_load((workspace / "workbench.yaml").read_text())
    inputs, missing = [], []
    for series, spec in config.get("series", {}).items():
        for episode, row in spec.get("episodes", {}).items():
            key = f"{series}/{episode}"
            report = overrides.get(key, previews / series / episode / "preview/preview.json")
            if report.is_dir(): report = report / "preview.json"
            if not report.is_file():
                missing.append(key); continue
            data = json.loads(report.read_text())
            inputs.append({"key": key, "project": str((workspace / row["project"]).resolve()),
                           "preview": str(report.resolve()),
                           "preview_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
                           "primary_view": data.get("primary_view", "unknown"),
                           "frames": data.get("frames", [])})
    # Use the same observer as the production preview, not a second formula.
    code = """
import {observeLayout} from './scripts/layout_observations.mjs';
let raw='';for await(const chunk of process.stdin)raw+=chunk;
const rows=JSON.parse(raw);
for(const row of rows)for(const frame of row.frames)
  frame.findings=observeLayout(frame.layout,1280,720);
process.stdout.write(JSON.stringify(rows));
"""
    result = subprocess.run(["node", "--input-type=module", "-e", code],
                            cwd=workspace, input=json.dumps(inputs), text=True, capture_output=True, check=True)
    inputs = json.loads(result.stdout)
    episodes, cases = [], []
    for item in inputs:
        grouped = {}
        for frame in item["frames"]:
            for finding in frame["findings"]:
                if finding["kind"] not in KINDS: continue
                signature = (frame.get("scene"), finding["kind"], finding.get("element"))
                group = grouped.setdefault(signature, {
                    "episode_key": item["key"], "scene": frame.get("scene"),
                    "kind": finding["kind"], "text": finding.get("element"),
                    "preview": item["preview"], "samples": [],
                    "review_status": "needs_visual_classification", "blocks_stage_progress": False})
                group["samples"].append({"time": frame["time"],
                    "frame": str(Path(item["preview"]).parent / frame["file"]), "finding": finding})
        for group in grouped.values():
            group["id"] = f"T{len(cases)+1:04d}"
            cases.append(group)
        episodes.append({"episode_key": item["key"], "project": item["project"],
                         "preview": item["preview"], "preview_sha256": item["preview_sha256"],
                         "primary_view": item["primary_view"],
                         "sampled_frames": len(item["frames"]), "candidate_groups": len(grouped),
                         "text_region_bindings": sum(len(f.get("layout", {}).get("textRegions", [])) for f in item["frames"]),
                         "review_status": ("final_text_view_not_evidenced" if item["primary_view"] != "final"
                                           else "needs_visual_classification" if grouped else "no_candidate_in_sampled_frames"),
                         "full_timeline_approved": False})
    output.mkdir(parents=True, exist_ok=True)
    data = {"schema": "text_layout_sample_review/v1", "episodes_checked": len(episodes),
            "missing_previews": missing, "candidate_groups": len(cases),
            "final_view_episodes": sum(row["primary_view"] == "final" for row in episodes),
            "non_final_previews": [row["episode_key"] for row in episodes if row["primary_view"] != "final"],
            "kind_counts": dict(Counter(c["kind"] for c in cases)), "episodes": episodes, "cases": cases,
            "note": "相交是定位线索；纸上标题、独立题注、操作叠压与真实缺陷须看原尺寸画面区分。无疑点仅指当前抽样，不代表全时间线通过。"}
    (output / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n")
    sheets_generated = make_sheets(cases, output)
    data["sheets_generated"] = sheets_generated
    # Crop sheets are optional visual aids.  Keep the structured frame/rect
    # report usable when Pillow is not installed in a minimal local runtime.
    (output / "report.json").write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n")
    lines = ["# 文字布局全季抽样复查", "", data["note"], "",
             f"登记单集 {len(episodes)}；缺预览 {len(missing)}；待目视归类 {len(cases)} 组。", "",
             "| 集数 | 主视图 | 检查帧 | 疑点组 | 状态 |", "| --- | --- | ---: | ---: | --- |"]
    for row in episodes:
        lines.append(f"| {row['episode_key']} | {row['primary_view']} | {row['sampled_frames']} | {row['candidate_groups']} | {row['review_status']} |")
    (output / "report.md").write_text("\n".join(lines)+"\n")
    print(json.dumps({k: data[k] for k in ("episodes_checked","missing_previews","candidate_groups","kind_counts")}, ensure_ascii=False))

def make_sheets(cases, output):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ModuleNotFoundError:
        return False
    candidates = ["/System/Library/Fonts/STHeiti Light.ttc", "C:/Windows/Fonts/msyh.ttc",
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    available = next((p for p in candidates if Path(p).is_file()), None)
    font = ImageFont.truetype(available, 16) if available else ImageFont.load_default()
    tiles = []
    for case in cases:
        sample = case["samples"][len(case["samples"])//2]
        path = Path(sample["frame"])
        if not path.is_file(): continue
        im = Image.open(path).convert("RGB")
        a = sample["finding"]["rect"]
        # Retain the nearby object, not just the glyphs, to reveal actual ownership.
        cx,cy = max(0,min(im.width,a["x"]+a["w"]/2)),max(0,min(im.height,a["y"]+a["h"]/2))
        w,h = max(360,a["w"]+130),max(170,a["h"]+130)
        box=(max(0,cx-w/2),max(0,cy-h/2),min(im.width,cx+w/2),min(im.height,cy+h/2))
        crop=im.crop(box);crop.thumbnail((600,220))
        tile=Image.new("RGB",(620,300),"white");tile.paste(crop,((620-crop.width)//2,70))
        draw=ImageDraw.Draw(tile)
        draw.text((8,6),case["id"]+" "+case["episode_key"],fill="black",font=font)
        draw.text((8,29),f"S{case['scene']} {sample['time']:.2f}s "+case["text"],fill="black",font=font)
        draw.text((8,50),case["kind"],fill="#556666",font=font)
        tiles.append(tile)
    for offset in range(0,len(tiles),12):
        batch=tiles[offset:offset+12]
        sheet=Image.new("RGB",(1240,300*((len(batch)+1)//2)),"#dedede")
        for i,tile in enumerate(batch):sheet.paste(tile,((i%2)*620,(i//2)*300))
        sheet.save(output/f"sheet-{offset//12+1:02d}.jpg",quality=94)
    return True

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace",type=Path,default=Path.cwd())
    parser.add_argument("--previews",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--override",action="append",default=[])
    args=parser.parse_args()
    overrides={k:Path(v) for k,v in (x.split("=",1) for x in args.override)}
    audit(args.workspace.resolve(),args.previews.resolve(),args.output.resolve(),overrides)
if __name__=="__main__":main()
