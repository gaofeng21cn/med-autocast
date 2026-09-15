"""Resource integrity checks, not semantic quality approval."""
import json
import re
from pathlib import Path
import yaml
R=Path(__file__).resolve().parents[1]
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
carrier=R/'plugins/opl-medcast/skills/opl-medcast'
assert primary.read_bytes()==(carrier/'SKILL.md').read_bytes(),'主Skill载体未同步'
# Shipped method copies must be byte-identical to current source and contain no stale files.
for dirname in ['agent','contracts','docs','runtime']:
    originals={str(p.relative_to(R)) for p in (R/dirname).rglob('*') if p.is_file() and '__pycache__' not in p.parts and not (dirname=='docs' and any(x in p.relative_to(R/'docs').parts for x in ['design','evidence']))}
    projected={str(p.relative_to(carrier)) for p in (carrier/dirname).rglob('*') if p.is_file()}
    assert originals==projected,('载体文件清单漂移',originals^projected)
    for rel in originals:assert (R/rel).read_bytes()==(carrier/rel).read_bytes(),('载体内容漂移',rel)
print(json.dumps({'status':'passed','stages':len(manifest['stages']),'professional_skills':len(list((R/'agent/professional_skills').glob('*/SKILL.md')))},ensure_ascii=False))
# Distribution identifiers and versions must agree before creating a release.
package=json.loads((R/'contracts/opl_agent_package_manifest.json').read_text())
market=json.loads((R/'.agents/plugins/marketplace.json').read_text())
plugin_root=R/'plugins/opl-medcast'
assert market['name']=='opl-medcast'
assert market['plugins'][0]['source']['path']=='./plugins/opl-medcast'
assert package['codex_surface']['configured_codex_plugin_carrier']['plugin_selector']=='opl-medcast@opl-medcast'
for path in [plugin_root/'plugin.json',plugin_root/'.codex-plugin/plugin.json']:
    plugin=json.loads(path.read_text())
    assert plugin['name']==package['codex_surface']['plugin_id']==market['plugins'][0]['name']
    assert plugin['version']==package['version']
print(json.dumps({'distribution_identity':'passed','version':package['version']}))
