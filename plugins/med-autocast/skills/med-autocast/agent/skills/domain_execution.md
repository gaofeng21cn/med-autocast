# 医学视频执行

根据当前请求选择 manifest 中阶段与专业 Skill。复用现有制作工作区已验证脚本，命令 cwd 为 workspace_root。OPL 编排阶段，Agent不自建 scheduler、队列或 session owner。依据实际产物决定下一阶段，已有可用结果允许跳转；质量欠项不阻止审看交付，但阻止无证据的 ready 声明。
