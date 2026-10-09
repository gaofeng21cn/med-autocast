#!/usr/bin/env python3
"""只读检查工作区的核心依赖；可选模型和内容审核不影响核心就绪状态。"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def command(name: str, args: list[str] | None = None) -> dict:
    path = shutil.which(name)
    result = {'state': 'ready' if path else 'missing', 'path': path}
    if path and args:
        try:
            completed = subprocess.run([path, *args], capture_output=True, text=True, timeout=10, check=True)
            result['version'] = (completed.stdout or completed.stderr).strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError) as exc:
            result.update(state='error', error=str(exc))
    return result


def node_playwright(root: Path) -> dict:
    fix = f'bash {shlex.quote(str(root / "scripts/setup_workbench.sh"))}'
    if not shutil.which('node'):
        return {'state': 'blocked', 'reason': 'node_missing', 'fix': fix}
    # Resolve from the workspace, not cwd or the installed plugin's cache.
    probe = """
const {createRequire} = require('node:module');
const fs = require('node:fs');
(async () => {
 let browser;
 try {
  const req = createRequire(require('node:path').resolve(process.argv[1], 'package.json'));
  const {chromium} = req('playwright');
  const executable = process.env.CHROME_PATH || chromium.executablePath();
  if (!fs.existsSync(executable)) throw new Error('Chromium 未安装: ' + executable);
  browser = await chromium.launch({headless:true, executablePath:executable});
  const page = await browser.newPage();
  await page.setContent('<canvas id="c" width="8" height="8"></canvas>');
  const canvas = await page.evaluate(() => !!document.querySelector('canvas').getContext('2d'));
  if (!canvas) throw new Error('Canvas 2D 不可用');
  console.log(JSON.stringify({state:'ready', executable, launch_verified:true}));
 } catch (e) { console.log(JSON.stringify({state:'missing', error:e.message})); }
 finally { if (browser) await browser.close(); }
})();
"""
    try:
        result = subprocess.run(['node', '-e', probe, str(root)], capture_output=True, text=True, timeout=30, check=True)
        return {**json.loads(result.stdout), 'runtime_root': str(root), 'fix': fix}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {'state': 'error', 'error': str(exc), 'fix': fix}


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
        if spec.get('kind') == 'indextts':
            def locate(value):
                p = Path(value)
                return p if p.is_absolute() else workspace / p
            root = locate(spec['root'])
            python = locate(spec.get('python') or str(root / '.venv/bin/python'))
            model = locate(spec['model_root'])
            reference = locate(expand(author.get('voice', {}).get('reference_audio') or ''))
            paths = {'runtime_root': root.is_dir(), 'python': python.is_file() and os.access(python, os.X_OK),
                     'model_config': (model / 'config.yaml').is_file(), 'reference_audio': reference.is_file()}
            return {**result, 'state': 'paths_present' if all(paths.values()) else 'missing',
                    'paths': paths, 'network_required': False,
                    'fix': '按 backends/indextts/README.md 准备独立运行时、完整权重和授权参考音频',
                    'next': '路径齐备后运行短旁白；权重完整性、设备兼容性与离线能力以真实推理为准'}
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
    for name in ('ffmpeg', 'ffprobe', 'magick', 'node', 'npm'):
        required[name] = command(name, ['--version'] if name in ('node', 'npm') else ['-version'])
        required[name]['fix'] = 'macOS: brew install node ffmpeg imagemagick；Linux: 安装对应发行版软件包'
    node = required['node']
    if node['state'] == 'ready':
        try:
            if int(node['version'].lstrip('v').split('.')[0]) < 20:
                node.update(state='missing', fix='安装 Node.js 20+（推荐当前 LTS）')
        except (KeyError, ValueError):
            node.update(state='error', fix='无法识别 Node.js 版本')
    packages = {}
    for name in ('yaml', 'PIL', 'edge_tts'):
        packages[name] = {'state': 'ready' if importlib.util.find_spec(name) else 'missing', 'fix': setup}
    for name in ('yaml', 'PIL'):
        required[name] = packages[name]
    try:
        from workbench_config import resolve_font
        font = resolve_font(root=workspace)
        required['font'] = {'state': 'ready', 'path': str(font)}
    except Exception as exc:  # A diagnostic must also report malformed user YAML.
        required['font'] = {'state': 'missing', 'error': str(exc),
                            'fix': '安装中文字体（如 Noto Sans CJK），或设置 WORKBENCH_FONT / 部署档案 tools.font'}
    required['playwright_chromium'] = node_playwright(workspace)
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
            'optional_media': {
                'edge_tts_fallback': {**packages['edge_tts'], 'network_required': True, 'synthesis_verified': False},
                'index_tts_local': {'state': 'not_probed', 'fix': '有授权声线时按 backends/indextts/README.md 独立安装并做短音频验收'},
                'whisper_alignment': {'state': 'not_probed', 'fix': '按需安装 requirements-alignment.txt 和模型'},
                'imagegen': {'state': 'session_dependent', 'fix': '使用会话 ImageGen Skill；或使用已审/授权网络素材'},
                'video_models': {'state': 'optional', 'fix': '仅显式选择 H3/Seedance 时配置'}},
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
