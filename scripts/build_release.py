"""Build versioned preview archives from an annotated, clean source commit."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])

version = json.loads((ROOT / 'contracts/opl_agent_package_manifest.json').read_text())['version']
tag = 'v' + version
if git('status', '--porcelain').strip():
    raise SystemExit('Release build requires a clean source checkout')
commit = git('rev-parse', 'HEAD').decode().strip()
if git('cat-file', '-t', tag).strip() != b'tag' or git('rev-parse', tag + '^{}').decode().strip() != commit:
    raise SystemExit('Release requires an annotated version tag at HEAD')
output = ROOT / 'dist' / tag
output.mkdir(parents=True, exist_ok=True)
source = output / f'opl-medcast-{version}-source.tar.gz'
git('archive', '--format=tar.gz', '--prefix=opl-medcast/', '-o', str(source), commit)
plugin = output / f'opl-medcast-{version}-codex-plugin.zip'
paths = git('ls-tree', '-r', '--name-only', commit).decode().splitlines()
with zipfile.ZipFile(plugin, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(paths):
        if name == '.agents/plugins/marketplace.json' or name.startswith('plugins/'):
            info = zipfile.ZipInfo('opl-medcast/' + name, (2026, 9, 15, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, git('show', f'{commit}:{name}'))
    install_info = zipfile.ZipInfo('opl-medcast/INSTALL.txt', (2026, 9, 15, 0, 0, 0))
    install_info.compress_type = zipfile.ZIP_DEFLATED
    install_info.external_attr = 0o100644 << 16
    archive.writestr(install_info,
        'OPL Med Cast ' + version + '\n\n'
        'From this directory:\n'
        'codex plugin marketplace add . --json\n'
        'codex plugin add opl-medcast@opl-medcast --json\n\n'
        'Python helpers require Python >=3.10 and PyYAML >=6,<7.\n'
        'Helper: plugins/opl-medcast/skills/opl-medcast/runtime/native_helpers/medcast.py\n'
        'Preview only; OPL hosted activation and independent qualification remain pending.\n'
        'Source: https://github.com/gaofeng21cn/opl-medcast/tree/' + tag + '\n')
checksums = output / 'SHA256SUMS'
checksums.write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in [source, plugin]))
print(json.dumps({'version': version, 'source_commit': commit, 'output': str(output),
                  'assets': [source.name, plugin.name, checksums.name]}, indent=2))
