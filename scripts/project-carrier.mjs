// Local carrier projection using the Framework scaffold generator. No installation.
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {pathToFileURL,fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const framework=process.env.OPL_FRAMEWORK_ROOT;
if(!framework) throw new Error('Set OPL_FRAMEWORK_ROOT to a compatible Framework source checkout');
execFileSync(process.execPath,[path.join(framework,'scripts/materialize-python-support.mjs'),'--module','file_hash','--target',path.join(root,'runtime/workbench/scripts/_opl_file_hash.py')]);
const {buildScaffoldFiles}=await import(pathToFileURL(path.join(framework,'src/authority/packages/standard-domain-agent-scaffold-template.ts')));
const ownerManifest=JSON.parse(fs.readFileSync(path.join(root,'contracts/opl_agent_package_manifest.json'),'utf8'));
const files=buildScaffoldFiles('med-autocast','Med Auto Cast').filter(f=>f.path.startsWith('plugins/'));
for(const f of files){
 const destination=path.join(root,f.path);fs.mkdirSync(path.dirname(destination),{recursive:true});
 const body=f.path.endsWith('/SKILL.md')?fs.readFileSync(path.join(root,'agent/primary_skill/SKILL.md')):f.content;
 if(f.path.endsWith('plugin.json')){const manifest=JSON.parse(body);manifest.version=ownerManifest.version;fs.writeFileSync(destination,JSON.stringify(manifest,null,2)+'\n');}
 else fs.writeFileSync(destination,body);
}
// Bundle source-relative support paths alongside the primary Skill. This preserves
// repo-relative references after the Skill carrier is installed in another host.
const skillRoot=path.join(root,'plugins/med-autocast/skills/med-autocast');
for(const name of ['agent','contracts','docs','runtime']){
 fs.rmSync(path.join(skillRoot,name),{recursive:true,force:true});
 fs.cpSync(path.join(root,name),path.join(skillRoot,name),{recursive:true,filter:p=>!p.split(path.sep).some(part=>['__pycache__','node_modules','dist'].includes(part))&&!p.includes(`${path.sep}design${path.sep}`)&&!p.endsWith(`${path.sep}design`)&&!p.includes(`${path.sep}evidence${path.sep}`)&&!p.endsWith(`${path.sep}evidence`)});
}
console.log(JSON.stringify({status:'projected',owner:'one-person-lab',generator:'buildScaffoldFiles',local_projection_only:true,installed:false}));

// Native carrier descriptor is a projection of the owner manifest.
const carrierDescriptor=structuredClone(ownerManifest);
carrierDescriptor.codex_surface.plugin_source_path='.';
fs.writeFileSync(path.join(root,'plugins/med-autocast/opl-package.json'),JSON.stringify(carrierDescriptor,null,2)+'\n');
const adapter=JSON.parse(fs.readFileSync(path.join(root,'app-contribution-adapter.json'),'utf8'));
for(const entry of [...Object.values(adapter.reads),...Object.values(adapter.actions)]){
 entry.argv=entry.argv.map(arg=>arg==='runtime/native_helpers/app_contribution.py'
   ? 'skills/med-autocast/runtime/native_helpers/app_contribution.py':arg);
}
fs.writeFileSync(path.join(root,'plugins/med-autocast/app-contribution-adapter.json'),JSON.stringify(adapter,null,2)+'\n');
