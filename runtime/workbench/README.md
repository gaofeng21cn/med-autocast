# 可移植工作台核心

此目录保留来源 Workbench 的通用脚本、后端部署方法、专业参考和模板。原始素材、个人档案、密钥、模型和本机运行记录不在包内。

在 Med Auto Cast 中按 [工具接入](../../docs/workspace-adapter.md) 使用；新实例参考 templates/workbench.example.yaml 和 profiles 模板。目录职责和资产流转见 [工作台目录结构与资产生命周期](docs/17_工作台目录结构与资产生命周期.md)。修改来源工具的业务行为时必须验证真实输入输出，不能仅缩短说明或复制名称来宣称能力等价。

源码适配仅将工作区根交给显式环境变量 MED_AUTOCAST_WORKSPACE_ROOT；原合成器、字幕、混音、质量合同和文案格式保持原实现。工作区已有脚本优先，明确 --bundled 才强制使用随包实现。初始化器会生成 `workspace.manifest.json` 与 `WORKSPACE.md`，已有工作区可用 `init_workbench.py --upgrade` 增量补目录和入口标记，不覆盖作品。

代码动画的 `audit_motion.py` 是非阻断式动作审片工具，`runtime_receipt.mjs` 由预览/渲染入口写入运行时与输入指纹。两者用于提高初稿和返修可复现性，不替代导演、连续动态、完整听感或医学判断。

初稿前可运行 `scripts/first_draft_preflight.py --project <单集工程> --pretty`，集中定位人物完整性、姿态尺度、复杂对象阅读面积和动画参考接线。它只生成候选/质量债报告，不阻断创作，也不签发视觉、听感、医学或发布通过。

新系列的稳定结构是 `content/<topic_id>/`、`productions/<series_id>/<episode_id>/`、`assets/`、`publish/<series_id>/`；`work/`、`output/`、`tmp/` 是不同生命周期的运行态。旧工作区可以保留历史路径，迁移前必须检索引用并保留恢复指针。
