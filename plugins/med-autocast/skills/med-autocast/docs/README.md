# Med Auto Cast 文档索引

本仓库遵循 [OPL 文档生命周期政策](https://github.com/gaofeng21cn/one-person-lab/blob/main/docs/policies/docs-lifecycle-policy.md)（该政策为家族级规则 owner）。

## 目录分工

- `docs/`：产品边界、当前能力状态、安装、工作台工具接入、制作与交付 SOP、外挂素材接入及通用方法适配。
- `agent/`：OPL 声明式领域包（主 Skill、专业 Skill、Stage、Prompt、Quality Gate 与制作策略）。
- `runtime/workbench/docs/`：随包分发的工作台长方法与制作细节规范，按需加载。

## 核心文档

| 文档 | 唯一职责 |
| --- | --- |
| [architecture.md](architecture.md) | 产品定位、不变量、关键决策、来源归属、知识分工、Mini App、Stage 交接与渲染分离架构 |
| [status.md](status.md) | 当前版本事实、已验证能力边界与未闭合独立验收项 |
| [installation.md](installation.md) | OPL OCI 安装、首次工作台环境准备、`pack_doctor` 检查与短链路烟测 |
| [workspace-adapter.md](workspace-adapter.md) | 工作台工具寻址、Mini App 读写接口、原制作单预检、单集知识登记与媒体生命周期 |
| [delivery-sop.md](delivery-sop.md) | 媒体后端调度、视听复核、中断恢复、成片打包与双平台单一最新版交付 |
| [media-assets-integration.md](media-assets-integration.md) | 外挂 `mac-media-assets` 发现与取用、人物尺度边界、策展撤回及工作区关键帧参考库 |
| [video-shotcraft方法适配.md](video-shotcraft方法适配.md) | `shot_recipe`、动作弧与反幻灯片审片方法的长期适配边界 |

## 本地维护与验证

修改文档、合同或随包资源后，先刷新原生 carrier 投影，再运行完整验证：

```bash
node scripts/project-carrier.mjs
scripts/verify.sh full
git diff --check
```
