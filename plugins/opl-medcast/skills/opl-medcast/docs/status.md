# 版本状态

OPL Med Cast 0.1.0 是首个公开预览版本，交付源码与 Codex 插件。包含三个动作、六个工作阶段、六个专业技能，以及工作区检查、资产检索和交付预检辅助程序。

本地验证通过 14 个行为测试、OPL 标准结构检查、接口生成、源码目录检查和辅助程序定位。只读接入现有制作工作区，识别五个系列、72 张关键帧和两个关联视频拒用条目；拒用视频的残留可用区间不会进入检索结果。未重新制作媒体。

该版本尚未完成 OPL Meta Agent 独立资格验证，也未进入 OPL 的 GHCR 稳定软件包渠道。Framework 的正式软件包发布清单尚未登记 opl-medcast。GitHub 预览版与 Codex 插件的发布、安装，不代表 OPL 托管运行激活或视频生产验收。

## 独立资格验证的断点

OPL Meta Agent 仅提交过一次 engineer-agent 请求，编号 medcast-create-20260915。请求在启动前返回 standard_agent_managed_checkout_not_launchable：描述符指定 opl-meta-agent@opl-meta-agent，本机安装记录为 opl-meta-agent@opl-meta-agent-local。随后查询相同运行编号，返回 FoundryRun does not exist。没有生成 AgentBlueprint、EvalSpec 或资格结果；当前实现由开发会话完成。

恢复时先由 Framework 维护方修复并回读安装身份映射，确认原请求没有持久运行，再沿原请求恢复工程流程。已有实现作为待评估输入。精确请求、原始来源和完整本机回执保存在维护者本地恢复档案，不随公开包分发。

## 验证环境

结构验证使用 Framework 0.3.5 已提交源码快照，提交为 9b27b96faad5443a36e281d94f2365856de67ed0。快照复用了主仓依赖，因此不属于完全锁定依赖的独立环境。它仅用于开发验证，不是产品运行依赖。公开构建摘要位于仓库 docs/evidence/local-build-readback.json，记录的是发布前验证时点。

生产媒体、完整听审、医学复核与平台上传仍由具体制作任务分别验收。
