"""Resource integrity checks, not semantic quality approval."""
import json
import re
import subprocess
from pathlib import Path
import yaml
R=Path(__file__).resolve().parents[1]
if (R/'.git').exists():
    tracked_dups = subprocess.check_output(
        ['git', '-C', str(R), 'ls-files', '--', 'plugins/med-autocast/skills', 'plugins/med-autocast/assets'],
        text=True,
    ).splitlines()
    assert not tracked_dups, ('投影副本不得提交进 Git，应由 scripts/project-carrier.mjs 构建期物化', tracked_dups[:5])
for p in (R/'contracts').glob('*.json'):json.loads(p.read_text())
manifest=json.loads((R/'agent/stages/manifest.json').read_text())
for stage in manifest['stages']:
    for ref in [stage['policy_ref'],stage['prompt_ref'],*stage['knowledge_refs'],*stage['quality_gate_refs'],*stage.get('skill_refs',[])]:
        assert (R/ref).is_file(),ref
for p in [R/'agent/primary_skill/SKILL.md',*sorted((R/'agent/professional_skills').glob('*/SKILL.md'))]:
    body=p.read_text();header=yaml.safe_load(body.split('---',2)[1]);assert header.get('name') and header.get('description'),p
    for target in re.findall(r'\]\(([^)]+)\)',body):
        if '://' not in target:assert (p.parent/target.split('#')[0]).resolve().is_file(),(p,target)
primary=R/'agent/primary_skill/SKILL.md'
carrier=R/'plugins/med-autocast/skills/med-autocast'
assert primary.read_bytes()==(carrier/'SKILL.md').read_bytes(),'主Skill载体未同步'
# Shipped method copies must be byte-identical to current source and contain no stale files.
for dirname in ['agent','contracts','docs','runtime']:
    originals={str(p.relative_to(R)) for p in (R/dirname).rglob('*') if p.is_file() and not any(part in p.parts for part in ['__pycache__','node_modules','dist']) and not (dirname=='docs' and any(x in p.relative_to(R/'docs').parts for x in ['design','evidence']))}
    projected={str(p.relative_to(carrier)) for p in (carrier/dirname).rglob('*') if p.is_file() and not any(part in p.parts for part in ['__pycache__','node_modules','dist'])}
    assert originals==projected,('载体文件清单漂移',originals^projected)
    for rel in originals:assert (R/rel).read_bytes()==(carrier/rel).read_bytes(),('载体内容漂移',rel)
print(json.dumps({'status':'passed','stages':len(manifest['stages']),'professional_skills':len(list((R/'agent/professional_skills').glob('*/SKILL.md')))},ensure_ascii=False))
# Distribution identifiers and versions must agree before creating a release.
plugin_root=R/'plugins/med-autocast'
package=json.loads((R/'opl-package.json').read_text())
companion=json.loads((R/'contracts/opl_agent_package_manifest.json').read_text())['capability_dependencies'][0]
market=json.loads((R/'.agents/plugins/marketplace.json').read_text())
assert market['name']=='med-autocast'
assert market['plugins'][0]['source']['path']=='./plugins/med-autocast'
assert package['schema_version']=='opl.package.v2'
assert package['identity']['id']=='med-autocast'
assert not (plugin_root/'opl-package.json').exists(), '根目录必须是唯一 OPL 包清单入口'
assert package['dependencies']['packages']==[{
    'id': companion['package_id'],
    'presence': 'required' if companion['required'] else 'optional',
    'required_capabilities': companion['required_export_ids'],
    'required_module_ids': companion['required_module_ids'],
}]
provides=package['provides']
assert (R / provides['agent']['stages_ref']).is_file()
assert (R / provides['skills'][0]['path'] / 'SKILL.md').is_file()
assert (R / provides['contribution_handler']['argv'][1]).is_file()
assert (R / provides['mcp_servers'][0]['args'][0]).is_file()
for path in [plugin_root/'plugin.json',plugin_root/'.codex-plugin/plugin.json']:
    plugin=json.loads(path.read_text())
    assert plugin['name']==package['identity']['id']==market['plugins'][0]['name']
    assert plugin['version']==package['identity']['version']
print(json.dumps({'distribution_identity':'passed','version':package['identity']['version']}))

# Portable resources must stay reachable after installation, not only in the source workbench.
for directory in ['agent/professional_skills','docs','runtime/workbench']:
    for p in (R/directory).rglob('*.md'):
        if any(part in p.parts for part in ['node_modules', '__pycache__', 'dist']):
            continue
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
            target=target.split('#')[0]
            if target and '://' not in target:
                assert (p.parent/target).resolve().exists(),('缺失方法资源',p,target)
import ast
for p in (R/'runtime').rglob('*.py'):
    ast.parse(p.read_text(),filename=str(p))
print(json.dumps({'portable_resource_links':'passed','runtime_syntax':'passed'}))
