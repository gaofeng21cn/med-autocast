"""Versioned local element storage; curation and creative approval stay model-owned."""

from __future__ import annotations

import copy
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import tempfile

import yaml

REFERENCE_KEYS = {
    "prompt_ref", "generation_receipt", "license_evidence", "medical_reference",
    "evidence_ref", "source_evidence_ref",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def digest(path):
    with Path(path).open("rb") as stream:
        result = hashlib.file_digest(stream, "sha256")
    return result.hexdigest()


def token(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise ValueError("素材库 ID 仅允许字母、数字、下划线和连字符")
    return value


def within(root, relative):
    root = Path(root).resolve()
    destination = (root / relative).resolve()
    if not destination.is_relative_to(root) or destination == root:
        raise ValueError("素材包路径越界")
    return destination


def references(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in REFERENCE_KEYS and isinstance(item, str):
                yield item
            else:
                yield from references(item)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)


def map_references(value, mapper):
    if isinstance(value, dict):
        return {key: mapper(item) if key in REFERENCE_KEYS and isinstance(item, str)
                else map_references(item, mapper) for key, item in value.items()}
    if isinstance(value, list):
        return [map_references(item, mapper) for item in value]
    return value


def archive(root, metadata, files):
    identifier = token(metadata["id"])
    descriptors = []
    sources = []
    for item in files:
        source = Path(item["source"]).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        relative = item.get("path") or ("files/" + source.name)
        within(root, relative)
        if relative in {"record.json", "library-record.json"}:
            raise ValueError("素材文件不能覆盖包记录")
        if any(row["path"] == relative for row in descriptors):
            raise ValueError("素材包内文件路径重复")
        descriptors.append({"path": relative, "role": item.get("role", "payload"),
                            "sha256": digest(source), "bytes": source.stat().st_size})
        sources.append(source)
    if not descriptors:
        return {"id": identifier, "status": "not_archived", "quality_debt": ["没有实际文件"]}
    metadata = {key: value for key, value in metadata.items() if key not in {"schema", "revision"}}
    body = {**metadata, "files": descriptors}
    within(root, metadata.get("entry", descriptors[0]["path"]))
    if metadata.get("entry") and metadata["entry"] not in {item["path"] for item in descriptors}:
        raise ValueError("素材入口必须是实际归档的文件")
    identity = json.dumps(body, ensure_ascii=False, sort_keys=True).encode()
    revision = hashlib.sha256(identity).hexdigest()[:20]
    destination = root / "entries" / identifier / revision
    record = {"schema": "animation_element/v1", **body, "revision": revision}
    if destination.exists():
        existing = read(destination / "record.json")
        if existing != record:
            raise ValueError("同一素材版本存在不同记录，保留原件")
        for item in descriptors:
            if digest(within(destination, item["path"])) != item["sha256"]:
                raise ValueError("已有素材包字节已变化")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".library-", dir=destination.parent) as temporary:
            staging = Path(temporary) / "package"
            staging.mkdir()
            for source, item in zip(sources, descriptors):
                target = within(staging, item["path"])
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                if digest(target) != item["sha256"]:
                    raise ValueError("素材复制字节不一致")
            write(staging / "record.json", record)
            staging.rename(destination)
    catalog_path = root / "catalog.json"
    catalog = read(catalog_path) if catalog_path.exists() else {"schema": "animation_element_library/v1", "items": []}
    relative = str((destination / "record.json").relative_to(root))
    if not any(row.get("record") == relative for row in catalog["items"]):
        catalog["items"].append({"id": identifier, "revision": revision, "record": relative})
        write(catalog_path, catalog)
    return {"id": identifier, "revision": revision, "record": relative, "status": "archived_and_verified"}


def ingest_project(workspace, root, project, selected=None, notes=None):
    project = within(workspace, project)
    config = read(project / "project.json")
    manifest = read(within(project, config.get("assets", "asset_manifest.json")))
    notes = notes or {}
    results, debts = [], []
    found = set()
    for asset in manifest.get("assets", []):
        asset_id = asset.get("asset_id")
        if not asset_id or (selected and asset_id not in selected):
            continue
        found.add(asset_id)
        extra = notes.get(asset_id, {})
        identifier = extra.get("id") or f"{config['series_id']}_{asset_id}"
        if not asset.get("path"):
            debts.append({"asset_id": asset_id, "detail": "素材没有实际路径"})
            continue
        original = within(project, asset["path"])
        paths = {asset["path"]: "files/payload" + original.suffix.lower()}
        files = [{"source": original, "path": paths[asset["path"]]}]
        unresolved = []
        for i, reference in enumerate(dict.fromkeys(references(asset))):
            if "://" in reference:
                continue
            evidence = (project / reference).resolve()
            if not evidence.is_relative_to(workspace):
                unresolved.append(reference)
            elif evidence.is_file():
                paths[reference] = f"evidence/{i}-{evidence.name}"
                files.append({"source": evidence, "path": paths[reference], "role": "evidence"})
            else:
                unresolved.append(reference)
        stored_asset = map_references(copy.deepcopy(asset), lambda ref: paths.get(ref, ref))
        stored_asset["path"] = paths[asset["path"]]
        metadata = {
            "id": identifier, "title": asset.get("visual_meaning") or asset_id,
            "kind": "image", "tags": ["paper_collage", asset_id],
            "entry": paths[asset["path"]], "asset": stored_asset,
            "source": {"project": str(project), "series": config["series_id"],
                       "episode": config["episode_id"], "asset_id": asset_id,
                       "original_manifest": asset},
            "reuse_scope": {"kind": "unclassified"},
            "quality_debt": [],
            **extra,
        }
        metadata["quality_debt"] = list(extra.get("quality_debt", [])) + ["未归档来源: " + ref for ref in unresolved]
        if not extra.get("reuse_scope"):
            metadata["quality_debt"].append("复用范围尚待策展")
        try:
            results.append(archive(root, metadata, files))
        except FileNotFoundError as error:
            debts.append({"asset_id": asset_id, "detail": str(error)})
    for missing in set(selected or []) - found:
        debts.append({"asset_id": missing, "detail": "不在当前素材清单中"})
    return results, debts


def register_records(root, path):
    path = Path(path).resolve()
    value = read(path)
    records = value.get("records", [value]) if isinstance(value, dict) else value
    results, debts = [], []
    for item in records:
        metadata = {key: field for key, field in item.items() if key != "files"}
        files = [{**file, "source": (path.parent / file["source"]).resolve()} for file in item.get("files", [])]
        if not metadata.get("id"):
            debts.append({"detail": "条目缺少可定位 ID", "record": metadata})
            continue
        try:
            results.append(archive(root, metadata, files))
        except FileNotFoundError as error:
            debts.append({"id": metadata["id"], "detail": str(error)})
    return results, debts


def managed_records(root):
    catalog = root / "catalog.json"
    latest, debts = {}, []
    if catalog.exists():
        for row in read(catalog).get("items", []):
            record_path = within(root, row["record"])
            try:
                record = read(record_path)
                if record["id"] != row["id"] or record["revision"] != row["revision"]:
                    raise ValueError("目录与包身份不一致")
                latest[record["id"]] = {**record, "record": row["record"], "managed": True,
                    "resolved_path": str(within(record_path.parent, record.get("entry", record["files"][0]["path"]))) }
            except (OSError, json.JSONDecodeError, KeyError, IndexError, ValueError) as error:
                debts.append({"record": row["record"], "detail": str(error)})
    return list(latest.values()), debts


def scan_projects(workspace):
    entries, debts = [], []
    config_path = workspace / "workbench.yaml"
    if not config_path.exists():
        return entries, [{"detail": "无工作台登记；仍可使用持久素材库"}]
    config = yaml.safe_load(config_path.read_text()) or {}
    for sid, series in config.get("series", {}).items():
        for eid, row in series.get("episodes", {}).items():
            if not row.get("project"):
                debts.append({"series": sid, "episode": eid, "detail": "单集未登记代码工程"})
                continue
            project = (workspace / row["project"]).resolve()
            if not project.is_relative_to(workspace):
                raise ValueError("登记项目路径越界")
            try:
                project_config = read(project / row.get("entry", "project.json"))
                manifest = read(project / project_config.get("assets", "asset_manifest.json"))
            except (OSError, json.JSONDecodeError) as error:
                debts.append({"project": str(project), "detail": str(error)})
                continue
            for item in manifest.get("assets", []):
                if not item.get("path"):
                    debts.append({"project": str(project), "detail": "素材没有实际路径"})
                    continue
                entries.append({**item, "id": sid + "_" + item.get("asset_id", "unclassified"),
                                "kind": "image", "series": sid, "episode": eid,
                                "project": str(project), "managed": False,
                                "resolved_path": str(within(project, item["path"]))})
    return entries, debts


def reuse(workspace, root, project, identifier, revision=None, asset_id=None):
    identifier = token(identifier)
    records, _ = managed_records(root)
    record = next((item for item in records if item["id"] == identifier), None)
    if revision:
        record_path = root / "entries" / identifier / token(revision) / "record.json"
        if not record_path.is_file():
            return {"status": "not_imported", "quality_debt": ["找不到所选素材版本"]}
        record = {**read(record_path), "record": str(record_path.relative_to(root))}
    if not record:
        return {"status": "not_imported", "quality_debt": ["找不到持久素材条目"]}
    scope = record.get("reuse_scope", {})
    project = within(workspace, project)
    config = read(project / "project.json")
    if scope.get("kind") == "author":
        from workbench_config import load_author_profile
        _, author = load_author_profile(root=workspace, series_id=config["series_id"])
        if author.get("profile_id") != scope.get("id"):
            return {"status": "not_imported", "quality_debt": ["作者身份与资产复用范围不一致"]}
    source = within(root, record["record"]).parent
    base = "src/library" if record.get("kind") in {"code_component", "motion_recipe"} else "assets/library"
    relative = Path(base) / identifier / record["revision"]
    destination = within(project, relative)
    asset = copy.deepcopy(record.get("asset"))
    manifest_path = project / config.get("assets", "asset_manifest.json")
    manifest = read(manifest_path) if asset else None
    new_id = token(asset_id or identifier) if asset else None
    existing = next((row for row in manifest["assets"] if row["asset_id"] == new_id), None) if asset else None
    if existing and existing.get("library_ref") != record["record"]:
        raise ValueError("目标素材 ID 已存在，保留原素材；请使用新 ID")
    for item in record["files"]:
        original = within(source, item["path"])
        target = within(destination, item["path"])
        if digest(original) != item["sha256"]:
            raise ValueError("素材库字节已变化，不能继续复用")
        if target.exists() and digest(target) != item["sha256"]:
            raise ValueError("目标目录有不同字节，不覆盖")
    for item in record["files"]:
        original = within(source, item["path"])
        target = within(destination, item["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        if digest(target) != item["sha256"]:
            raise ValueError("复用复制字节不一致")
    write(destination / "library-record.json", {key: value for key, value in record.items() if key != "resolved_path"})
    if asset and not existing:
        asset = map_references(asset, lambda ref: str(relative / ref) if (source / ref).is_file() else ref)
        asset.update({"asset_id": new_id, "path": str(relative / record["entry"]),
                      "source_type": "reviewed_library", "library_ref": record["record"],
                      "original_source_type": record["asset"].get("source_type"),
                      "source_review": copy.deepcopy(asset.get("visual_review", {})),
                      "status": "pending_review", "visual_review": {"status": "pending"}})
        if asset.get("medical"):
            asset["medical_review"] = {"status": "pending"}
        manifest["assets"].append(asset)
        write(manifest_path, manifest)
    usage_path = root / "uses.json"
    usage = read(usage_path) if usage_path.exists() else {"schema": "animation_element_uses/v1", "uses": []}
    use = {"id": identifier, "revision": record["revision"], "project": str(project.relative_to(workspace)),
           "series": config["series_id"], "episode": config["episode_id"], "asset_id": new_id,
           "directory": str(destination.relative_to(workspace))}
    if use not in usage["uses"]:
        usage["uses"].append(use)
        write(usage_path, usage)
    return {"status": "copied_and_verified", "id": identifier, "revision": record["revision"],
            "directory": str(destination), "entry": str(destination / record.get("entry", record["files"][0]["path"])),
            "asset_id": new_id, "review": "evaluate_in_current_shot",
            "quality_debt": record.get("quality_debt", []),
            "dependencies": record.get("dependencies", [])}


def board(root, records):
    cards = []
    kind_labels = {"image": "透明图像", "environment": "环境板", "code_component": "代码组件",
                   "motion_recipe": "动作方法", "audio": "声音分轨", "music_score": "配乐工程", "brand": "作者品牌"}
    for item in records:
        package = within(root, item["record"]).parent
        path = within(package, item.get("entry", item["files"][0]["path"]))
        source = str(path.relative_to(root))
        media = ""
        poster = next((file["path"] for file in item["files"] if file["role"] == "poster"), None)
        sample = next((file["path"] for file in item["files"] if file["role"] == "sample"), None)
        if path.suffix.lower() in IMAGE_SUFFIXES:
            media = f'<div class="image"><img loading="lazy" src="{html.escape(source)}" alt=""></div>'
        elif sample and Path(sample).suffix.lower() in {".mp4", ".webm"}:
            preview = html.escape(str((package / sample).relative_to(root)))
            poster_attr = f' poster="{html.escape(str((package / poster).relative_to(root)))}"' if poster else ""
            media = f'<video controls muted playsinline preload="none"{poster_attr} src="{preview}"></video>'
        elif path.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg"}:
            media = f'<audio controls preload="none" src="{html.escape(source)}"></audio>'
        elif poster:
            media = f'<div class="image"><img loading="lazy" src="{html.escape(str((package / poster).relative_to(root)))}" alt=""></div>'
        scope = item.get("reuse_scope", {})
        scope_label = {"general": "通用", "topic": "选题", "series": "系列", "author": "作者", "unclassified": "待归类"}.get(scope.get("kind"), scope.get("kind", "待归类"))
        status = item.get("asset", {}).get("status") or item.get("review_status", "待审")
        status = {"approved_direct_use": "原件视觉已查", "pending_review": "素材待审"}.get(status, status)
        if item.get("asset", {}).get("medical") and item["asset"].get("medical_review", {}).get("status") != "passed":
            status += " · 医学待审"
        search = html.escape(json.dumps(item, ensure_ascii=False).lower(), quote=True)
        kind_label = kind_labels.get(item.get("kind"), item.get("kind", "待归类"))
        cards.append(f'<article data-search="{search}" data-kind="{html.escape(item.get("kind", "unclassified"))}" data-scope="{html.escape(scope.get("kind", "unclassified"))}">{media}<h2>{html.escape(item.get("title", item["id"]))}</h2><div class="meta">{html.escape(kind_label)} · {scope_label} · {html.escape(status)}</div><p>{html.escape(item.get("usage_notes", ""))}</p><code>{html.escape(item["id"])}<br>{html.escape(item["revision"])}</code><nav><a href="{html.escape(source)}">原文件</a><a href="{html.escape(item["record"])}">来源与版本</a></nav></article>')
    kinds = sorted({item.get("kind", "unclassified") for item in records})
    options = ''.join(f'<option value="{html.escape(kind)}">{html.escape(kind_labels.get(kind, kind))}</option>' for kind in kinds)
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>纸剧场素材库</title>
<style>*{box-sizing:border-box}body{margin:0;font:15px system-ui;color:#25292b;background:#f1f3f3;letter-spacing:0}header{padding:20px 24px;background:#fff;border-bottom:1px solid #ccd2d2}h1{margin:0 0 14px;font-size:23px}form{display:flex;flex-wrap:wrap;gap:10px;align-items:center}input,select{font:inherit;padding:8px;max-width:100%;border:1px solid #a5b0b0;border-radius:4px}input{min-width:200px;flex:1}main{padding:20px 24px;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px}article{border:1px solid #ccd2d2;border-radius:6px;padding:14px;background:#fff;min-width:0}article[hidden]{display:none}h2{font-size:17px;line-height:1.5;margin:12px 0 4px;overflow-wrap:anywhere}.image,video{width:100%;aspect-ratio:4/3;display:block;overflow:hidden;background:#e4e9e8}.image{display:grid;place-items:center;background-image:linear-gradient(45deg,#ccc 25%,transparent 25%),linear-gradient(-45deg,#ccc 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#ccc 75%),linear-gradient(-45deg,transparent 75%,#ccc 75%);background-size:20px 20px;background-position:0 0,0 10px,10px -10px,-10px 0}.image img{width:100%;height:100%;object-fit:contain}audio{width:100%}.meta{color:#535b60;font-size:13px}p{line-height:1.6;overflow-wrap:anywhere}code{display:block;font-size:12px;overflow-wrap:anywhere}nav{display:flex;gap:20px;margin-top:12px}a{color:#196363}output{font-size:13px;color:#535b60}@media(max-width:500px){header,main{padding:14px}}</style>
<header><h1>纸剧场素材库</h1><form onsubmit="return false"><input id="query" type="search" aria-label="检索素材" placeholder="检索素材"><select id="kind" aria-label="素材类型"><option value="">全部类型</option>''' + options + '''</select><select id="scope" aria-label="复用范围"><option value="">全部范围</option><option value="general">通用</option><option value="topic">选题</option><option value="series">系列</option><option value="author">作者</option></select><select id="matte" aria-label="透明素材底色"><option value="">透明格</option><option value="#f4f5f5">浅底</option><option value="#303437">深底</option><option value="#b6c8d6">彩底</option></select><output id="count"></output></form></header><main>''' + ''.join(cards) + '''</main><script>const cards=[...document.querySelectorAll('article')],query=document.querySelector('#query'),kind=document.querySelector('#kind'),scope=document.querySelector('#scope');function filter(){let n=0;for(const card of cards){card.hidden=!(card.dataset.search.includes(query.value.toLowerCase())&&(!kind.value||kind.value===card.dataset.kind)&&(!scope.value||scope.value===card.dataset.scope));if(!card.hidden)n++}document.querySelector('#count').textContent=n+' 项'}query.oninput=kind.onchange=scope.onchange=filter;document.querySelector('#matte').onchange=e=>{for(const box of document.querySelectorAll('.image')){box.style.backgroundImage=e.target.value?'none':'';box.style.backgroundColor=e.target.value||''}};filter();</script></html>'''
    (root / "index.html").write_text(page)


def run(args):
    workspace = args.workspace.resolve()
    root = workspace / "assets/paper-theatre"
    actions, debts = [], []
    if getattr(args, "ingest_project", False):
        if not args.project:
            raise ValueError("归档需选择实际 --project")
        notes_path = getattr(args, "notes", None)
        notes = read(notes_path) if notes_path else {}
        actions, debts = ingest_project(workspace, root, args.project, getattr(args, "asset_id", None), notes)
    elif getattr(args, "register", None):
        actions, debts = register_records(root, args.register.resolve())
    elif getattr(args, "use", None):
        if not args.project:
            raise ValueError("复用需选择实际 --project")
        selected = getattr(args, "asset_id", None) or []
        actions = [reuse(workspace, root, args.project, args.use, getattr(args, "revision", None), selected[0] if selected else None)]
    managed, managed_debts = managed_records(root)
    live, live_debts = scan_projects(workspace)
    source_keys = {(item.get("source", {}).get("project"), item.get("source", {}).get("asset_id")) for item in managed}
    all_entries = managed + [item for item in live if (item["project"], item.get("asset_id")) not in source_keys]
    if getattr(args, "refresh", False) or getattr(args, "ingest_project", False) or getattr(args, "register", None):
        write(root / "index.json", {"schema": "animation_element_index/v1", "assets": all_entries, "quality_debt": managed_debts + live_debts})
        board(root, managed)
    query = (getattr(args, "query", None) or "").lower()
    kind, scope = getattr(args, "kind", None), getattr(args, "scope", None)
    matches = [item for item in all_entries if (not query or query in json.dumps(item, ensure_ascii=False).lower())
               and (not kind or item.get("kind") == kind)
               and (not scope or item.get("reuse_scope", {}).get("kind") == scope)]
    action_debts = [debt for action in actions for debt in action.get("quality_debt", [])]
    return {"status": "completed_with_quality_debt" if debts or managed_debts or live_debts or action_debts else "completed",
            "count": len(matches), "managed_count": len(managed), "assets": matches, "actions": actions,
            "catalog": str(root / "catalog.json"), "index": str(root / "index.json"),
            "board": str(root / "index.html"), "quality_debt": debts + managed_debts + live_debts + action_debts}
