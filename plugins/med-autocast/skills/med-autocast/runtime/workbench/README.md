# 可移植工作台核心

此目录保留来源 Workbench 的通用脚本、后端部署方法、专业参考和模板。原始素材、个人档案、密钥、模型和本机运行记录不在包内。

在 Med Auto Cast 中按 [工具接入](../../docs/workspace-adapter.md) 使用；新实例参考 templates/workbench.example.yaml 和 profiles 模板。修改来源工具的业务行为时必须验证真实输入输出，不能仅缩短说明或复制名称来宣称能力等价。

源码适配仅将工作区根交给显式环境变量 MED_AUTOCAST_WORKSPACE_ROOT；原合成器、字幕、混音、质量合同和文案格式保持原实现。工作区已有脚本优先，明确 --bundled 才强制使用随包实现。
