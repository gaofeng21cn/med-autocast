#!/usr/bin/env python3
"""只读检查工作区的核心依赖；可选模型和内容审核不影响核心就绪状态。"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from _opl_framework_bootstrap import bootstrap_opl_framework

bootstrap_opl_framework()

from opl_framework.dependency_probe import (  # noqa: E402
    probe_cli_command,
    probe_node_playwright,
    probe_python_module,
    probe_workspace_venv_python,
)

ROOT = Path(__file__).resolve().parents[1]


def command(name: str, args: list[str] | None = None) -> dict:
    probed = probe_cli_command(
        name,
        version_args=args,
        extra_paths=(),
        timeout_s=10,
        which=shutil.which,
        runner=subprocess.run,
    )
    result = {'state': probed['state'], 'path': probed['path']}
    if probed['state'] == 'ready' and args and probed.get('version') is not None:
        result['version'] = probed['version']
    elif probed['state'] == 'error':
        result['error'] = probed['detail']
    return result


def node_playwright(root: Path) -> dict:
    fix = f'bash {shlex.quote(str(root / "scripts/setup_workbench.sh"))}'
    probed = probe_node_playwright(
        repo_root=root,
        which=shutil.which,
        runner=subprocess.run,
        timeout_s=30,
    )
    if probed['state'] == 'blocked':
        return {'state': 'blocked', 'reason': probed.get('reason', 'node_missing'), 'fix': fix}
    if probed['state'] == 'error':
        return {'state': 'error', 'error': probed.get('error', probed.get('detail')), 'fix': fix}
    output = {k: v for k, v in probed.items() if k not in ('ok', 'detail', 'executable_path', 'canvas_ok')}
    output.update(runtime_root=str(root), fix=fix)
    return output


def node_remotion(root: Path) -> dict:
    fix = f'bash {shlex.quote(str(root / "scripts/setup_workbench.sh"))}'
    node_bin = shutil.which('node')
    if not node_bin:
        return {'state': 'blocked', 'reason': 'node_missing', 'fix': fix}
    probe_js = """
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const root = path.resolve(process.argv[1]);
const roots = [process.env.MED_AUTOCAST_REMOTION_ROOT, root].filter(Boolean);
const pkgs = ['remotion', '@remotion/bundler', '@remotion/renderer'];
const versions = {};
const missing = [];
for (const name of pkgs) {
  let found = false;
  for (const base of roots) {
    const pkgJson = path.join(base, 'package.json');
    const directMeta = path.join(base, 'node_modules', name, 'package.json');
    try {
      const req = createRequire(fs.existsSync(pkgJson) ? pkgJson : path.join(base, '__probe__.cjs'));
      const resolved = req.resolve(name);
      if (resolved) {
        if (fs.existsSync(directMeta)) {
          versions[name] = JSON.parse(fs.readFileSync(directMeta, 'utf8')).version;
        } else {
          versions[name] = 'installed';
        }
        found = true;
        break;
      }
    } catch {}
  }
  if (!found) missing.push(name);
}
console.log(JSON.stringify({ state: missing.length ? 'missing' : 'ready', missing, versions }));
"""
    try:
        proc = subprocess.run(
            [node_bin, '--input-type=module', '-e', probe_js, str(root)],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        payload = json.loads(proc.stdout.strip())
        payload.update(runtime_root=str(root), fix=fix)
        return payload
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {'state': 'error', 'error': str(exc), 'runtime_root': str(root), 'fix': fix}


def ffmpeg_libass(ffmpeg_entry: dict) -> dict:
    if ffmpeg_entry.get('state') != 'ready':
        return {
            'state': 'missing',
            'renderer': 'pysubs2_pillow_overlay',
            'fix': '先确保 ffmpeg 可用；如需 libass 硬字幕滤镜，请安装含 --enable-libass 的 ffmpeg',
        }
    try:
        proc = subprocess.run(
            ['ffmpeg', '-hide_banner', '-filters'],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        supported = bool(re.search(r'^\s*[T.S]{2,3}\s+ass\s+V->V\b', proc.stdout, re.MULTILINE))
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            'state': 'error',
            'renderer': 'pysubs2_pillow_overlay',
            'error': str(exc),
            'fix': '安装含 libass 的 ffmpeg，否则字幕阶段回退 pysubs2 Pillow 透明叠层',
        }
    if supported:
        return {'state': 'ready', 'renderer': 'ffmpeg_libass'}
    return {
        'state': 'fallback_only',
        'renderer': 'pysubs2_pillow_overlay',
        'fix': '当前 ffmpeg 不含 libass ass 滤镜，将使用 pysubs2 + Pillow 透明叠层（推荐 brew install ffmpeg-full）',
    }


def narration_dependencies(workspace: Path, packages: dict) -> dict:
    """Check the selected voice without loading models or contacting a provider."""
    try:
        from media_backend import expand
        from workbench_config import load_author_profile, load_backend_profile, select_audio_backend
        _, author = load_author_profile(root=workspace)
        _, backends = load_backend_profile(root=workspace)
        selected = select_audio_backend(author, backends)
        spec = expand(backends['audio'][selected])
        result = {'backend': selected, 'definition': spec.get('definition'), 'synthesis_verified': False}
        if spec.get('definition') == 'edge_tts':
            return {**result, 'state': 'dependencies_present' if packages['edge_tts']['state'] == 'ready' else 'missing',
                    'network_required': True, 'fix': packages['edge_tts']['fix'],
                    'next': '用固定参数合成短旁白，核对完整音轨与语气；包已安装不代表在线服务可用'}
        if spec.get('kind') == 'voxcpm':
            def locate(value):
                p = Path(value)
                return p if p.is_absolute() else workspace / p
            runtime = locate(spec['root'])
            python = locate(spec.get('python') or str(runtime / '.venv/bin/python'))
            model = locate(spec['model_root'])
            reference = locate(expand(author.get('voice', {}).get('reference_audio') or ''))
            paths = {
                'runtime_root': runtime.is_dir(),
                'python': python.is_file() and os.access(python, os.X_OK),
                'model_config': (model / 'config.json').is_file(),
                'model_weights': (model / 'model.safetensors').is_file(),
                'audio_vae': (model / 'audiovae.pth').is_file(),
                'reference_audio': reference.is_file(),
            }
            package = 'missing'
            version = None
            if paths['python']:
                try:
                    probe = subprocess.run([str(python), '-c', 'import importlib.metadata; print(importlib.metadata.version("voxcpm"))'], capture_output=True, text=True, timeout=10, check=True)
                    version = probe.stdout.strip()
                    package = 'ready'
                except (OSError, subprocess.SubprocessError):
                    package = 'missing'
            ready = all(paths.values()) and package == 'ready'
            return {**result, 'state': 'paths_present' if ready else 'missing',
                    'paths': paths, 'package': package, 'package_version': version,
                    'network_required': False,
                    'fix': '按 backends/voxcpm/README.md 准备 VoxCPM2 独立运行时、完整权重和授权参考音频',
                    'next': '路径齐备后运行真实短旁白；模型加载、MPS 稳定性和发音听辨以实际合成与人工审听为准'}
        return {**result, 'state': 'not_probed', 'next': '按登记的后端运行短旁白验收'}
    except Exception as exc:
        return {'state': 'needs_setup', 'synthesis_verified': False, 'error': str(exc),
                'fix': '修正作者声音与部署档案，再运行 environment_check'}


def check(workspace: Path) -> dict:
    workspace = workspace.resolve()
    setup = f'bash {shlex.quote(str(workspace / "scripts/setup_workbench.sh"))}'
    try:
        from workspace_layout import status as layout_status
        layout = layout_status(workspace)
    except Exception as exc:  # Keep diagnostics useful for older workspaces.
        layout = {'state': 'unknown', 'error': str(exc), 'repairable': True}
    required = {
        'python_3_11': {'state': 'ready' if sys.version_info >= (3, 11) else 'missing',
                        'version': platform.python_version(), 'interpreter': sys.executable, 'fix': '安装 Python 3.11+'},
    }
    for name in ('ffmpeg', 'ffprobe', 'magick', 'node', 'npm', 'cwebp'):
        required[name] = command(name, ['--version'] if name in ('node', 'npm') else ['-version'])
        required[name]['fix'] = 'macOS: brew install node ffmpeg imagemagick webp flac；Linux: 安装对应发行版软件包'
    node = required['node']
    if node['state'] == 'ready':
        try:
            if int(node['version'].lstrip('v').split('.')[0]) < 20:
                node.update(state='missing', fix='安装 Node.js 20+（推荐当前 LTS）')
        except (KeyError, ValueError):
            node.update(state='error', fix='无法识别 Node.js 版本')
    packages = {}
    for name in ('yaml', 'PIL', 'pysubs2', 'pyloudnorm', 'soundfile', 'numpy', 'edge_tts'):
        mod_probe = probe_python_module(name, find_spec=importlib.util.find_spec)
        present = bool(mod_probe['ok'])
        source = 'system' if present else None
        if not present:
            venv_probe = probe_workspace_venv_python(
                workspace,
                required_modules=(name,),
                runner=subprocess.run,
                timeout_s=10,
            )
            present = bool(venv_probe['modules'].get(name))
            source = 'workspace_venv' if present else None
        packages[name] = {'state': 'ready' if present else 'missing', 'source': source, 'fix': setup}
    for name in ('yaml', 'PIL', 'pysubs2', 'pyloudnorm', 'soundfile', 'numpy'):
        required[name] = packages[name]
    try:
        from workbench_config import resolve_font
        font = resolve_font(root=workspace)
        required['font'] = {'state': 'ready', 'path': str(font)}
    except Exception as exc:  # A diagnostic must also report malformed user YAML.
        required['font'] = {'state': 'missing', 'error': str(exc),
                            'fix': '安装中文字体（如 Noto Sans CJK），或设置 WORKBENCH_FONT / 部署档案 tools.font'}
    required['playwright_chromium'] = node_playwright(workspace)
    required['remotion'] = node_remotion(workspace)
    libass_probe = ffmpeg_libass(required['ffmpeg'])
    try:
        from workbench_config import validate
        config = validate(root=workspace)
        configuration = {'state': 'ready' if config['status'] == 'passed' else 'needs_setup', 'errors': config['errors']}
    except Exception as exc:  # A diagnostic must also report malformed user YAML.
        configuration = {'state': 'needs_setup', 'errors': [str(exc)]}
    configuration['fix'] = '新目录使用 setup_workbench.sh --workspace <目录>；已有工作区按错误修正档案，不覆盖'
    ready = all(item['state'] == 'ready' for item in required.values())
    narration = narration_dependencies(workspace, packages)
    configured = ready and configuration['state'] == 'ready'
    environment_ready = configured and narration['state'] not in ('missing', 'needs_setup')
    return {'schema': 'med_autocast_environment/v1', 'read_only': True, 'workspace': str(workspace),
            'workspace_layout': layout,
            'platform': platform.platform(), 'required': required, 'configuration': configuration,
            'selected_narration': narration,
            'subtitle_renderer_capability': libass_probe,
            'optional_media': {
                'ffmpeg_libass': libass_probe,
                'edge_tts_fallback': {**packages['edge_tts'], 'network_required': True, 'synthesis_verified': False},
                'whisper_alignment': {'state': 'not_probed', 'fix': '按需安装 requirements-alignment.txt 和模型'},
                'imagegen': {'state': 'session_dependent',
                             'fix': '使用调用方会话提供的 ImageGen 能力；MAC 负责素材准入与回执登记'},
                'video_models': {'state': 'optional', 'fix': '仅显式选择已部署、workflow 齐备且可达的 ComfyUI H3 时配置'}},
            'status': 'ready' if environment_ready else 'needs_setup',
            'core_ready': ready, 'production_ready': False,
            'next': '环境通过；先确定作者形象与声线并制作短样片' if environment_ready else '按未就绪项的 fix 修复后重新检查'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(os.environ.get('MED_AUTOCAST_WORKSPACE_ROOT', ROOT)))
    parser.add_argument('--pretty', action='store_true')
    parser.add_argument('--strict', action='store_true', help='未就绪时退出码为 1')
    args = parser.parse_args()
    report = check(args.workspace)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    if args.strict and report['status'] != 'ready':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
