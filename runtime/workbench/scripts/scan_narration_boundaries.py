#!/usr/bin/env python3
"""Verify actual narration bytes and timing; metadata alone never proves repair."""
from __future__ import annotations
import argparse, hashlib, json, wave
from pathlib import Path

def current_projects(workspace: Path):
    import yaml
    config = yaml.safe_load((workspace / "workbench.yaml").read_text()) or {}
    seen=[]
    for series in (config.get("series") or {}).values():
        for episode in (series.get("episodes") or {}).values():
            project=episode.get("project")
            if project:
                p=(workspace/project).resolve()
                if p.is_dir() and p not in seen: seen.append(p)
    return seen

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def duration(path):
    with wave.open(str(path)) as handle: return handle.getnframes()/handle.getframerate()

def inspect(project):
    data=json.loads((project/"audio/narration_beats.json").read_text()); splice=data.get("splice",{})
    raw,norm=project/"audio/narration.wav",project/"audio/narration-normalized.wav"; flags=[]
    if splice.get("schema")!="narration_splice/v2": flags.append("legacy_splice_requires_actual_lineage_review")
    if not raw.is_file() or not norm.is_file(): flags.append("missing_voice_track")
    else:
        if abs(duration(raw)-duration(norm))>1/24000: flags.append("raw_and_normalized_timeline_disagree")
        if abs(duration(norm)-float(data.get("duration",-1)))>.001: flags.append("receipt_duration_not_actual_voice_duration")
        for name,path in (("raw_sha256",raw),("normalized_sha256",norm)):
            if splice.get(name)!=sha(path): flags.append(f"{name}_unbound_or_changed")
    for beat in data.get("beats",[]):
        source=Path(beat["audio"]); source=source if source.is_absolute() else project/source
        if not source.is_file(): flags.append(f"{beat['id']}:missing_source"); continue
        if beat.get("source_sha256") and beat["source_sha256"]!=sha(source): flags.append(f"{beat['id']}:source_changed")
        if splice.get("policy")=="resample_correctly_preserve_all_source_samples" and abs(beat["end"]-beat["start"]-duration(source))>.001:
            flags.append(f"{beat['id']}:source_duration_not_retained")
    return {"project":str(project),"beats":len(data.get("beats",[])),"flags":flags,
            "status":"source_timeline_bound" if not flags else "needs_repair",
            "final_mp4_lineage":"run audit_narration_lineage.py on actual current output",
            "full_listening":"pending"}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--workspace",type=Path,default=Path.cwd()); p.add_argument("--apply",action="store_true"); p.add_argument("--repair-normalized",action="store_true"); p.add_argument("--backup-root",type=Path); p.add_argument("--report",type=Path); a=p.parse_args(); workspace=a.workspace.resolve(); rows=[]
    for project in current_projects(workspace):
        if not (project/"audio/narration_beats.json").is_file(): continue
        row=inspect(project)
        if (a.apply or a.repair_normalized) and row["flags"]:
            from rebuild_narration_lossless import rebuild
            backup=a.backup_root or workspace/"work/narration-lineage-backups"; row["repair"]=rebuild(project,backup.resolve()); row={**inspect(project),"repair":row["repair"]}
        rows.append(row)
    summary={"schema":"narration_boundary_scan/v2","episodes_checked":len(rows),"source_timeline_bound":sum(not r["flags"] for r in rows),"needing_repair":sum(bool(r["flags"]) for r in rows),"applied":a.apply or a.repair_normalized,"detail":rows,"note":"Source timeline binding is not full listening or final MP4 approval."}
    if a.report: a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
