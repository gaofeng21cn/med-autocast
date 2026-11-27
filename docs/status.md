# 当前能力与验证范围

## 源码与载体现状

- **软件包版本**：当前源码与 manifest 版本以根目录 `opl-package.json`（`opl.package.v2`）为准；通过 `scripts/project-carrier.mjs` 依据 `contracts/carrier_projection.json` 将随包资源与 Codex 插件元数据投影至 `plugins/med-autocast/`。
- **核心能力边界**：
  - 声明式领域包覆盖六个核心 Stage、可选 `asset-curation` 后置沉淀以及对应专业 Skill，随包提供工作台 `runtime/workbench` 核心脚本、模板与长方法 SOP。
  - 默认视觉路线为本地 JavaScript 手绘拼贴（`paper_collage + canvas2d`），支持 `shot_recipe`、角色表演与镜头语言、可恢复三态媒体生命周期治理以及 `publish/` 单一最新版双平台交付。
  - 旁白默认在工作区使用作者授权的 VoxCPM2 参考声线，未提供或主动跳过时回退至需联网的 Edge TTS；图像素材由调用方会话 ImageGen 或外挂 `mac-media-assets` 提供，通用源码与文档不写死个人品牌、作者声线或部署主机。
  - 环境诊断声明见 `contracts/pack_doctor.json`，工作台便携工具通过 `runtime/workbench/scripts/_opl_framework_bootstrap.py` 与 `_opl_file_hash.py` 对齐 Framework helper，独立制作工作区不强依赖安装 Framework。
  - 独立 `mac-media-assets` 作为 required 能力依赖随标准 OPL 安装自动解析，未安装或离线环境下按 Progress First 保留可读诊断。

## 本地已验证范围

- `scripts/verify.sh fast` / `full` 覆盖 Python 单元测试、Stage/Skill/资源链接一致性（`scripts/verify_contracts.py`）、原生插件投影校验、工作区源码洁净度检查与 native helper 探针。
- 隔离测试覆盖字幕偏移、工作台工具寻址、原制作单/交付包预检、三态媒体保留与无损回收、单集审看交付与回读、以及基于共享 `window.__seek(t)` 的本地渲染与混音链路（依赖外部浏览器或 Pillow 的用例在缺少环境时明确跳过，不计作通过）。

## 独立未闭合验收边界

- **独立 OMA 资格与评测**：源码单元测试、合同校验与结构检查不替代独立 OMA FoundryRun、AgentBlueprint 或 EvalSpec 资格验收；历史开发验证留存 Git 记录。
- **作品内容与发布审核**：工程校验、构建通过或文件存在不代表真实作品的连续动态、完整听感、医生医学终审或平台公开上传授权；这些状态均按单集与发布任务分别回读。
- **OCI 发布与安装态回读**：源码更新不代表已发布 OCI artifact 或已安装本机插件已同步；发布与安装状态以 immutable ref、OPL Package 回读及对应载体检查为准。
