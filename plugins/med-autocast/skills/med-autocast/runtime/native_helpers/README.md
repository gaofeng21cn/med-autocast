# 工作台辅助入口

med_autocast.py 的 inspect、assets、tools、preflight-workbench 和兼容 preflight 均只读。workbench_tool.py 显式同步执行一个已授权工具，实际副作用由工具决定；不会自动选择生成、部署或上传，也不创建调度器。

安装后的路径同源于 Skill 根，工作区始终通过 --workspace 指定。完整调用和依赖说明见 ../../docs/workspace-adapter.md。

`app_contribution.py` 是 Mini App 的 owner 入口：`status/media` 只读，`note` 写入绑定当前版本的审看意见。它从 Framework 的 `OPL_PROFILE_WORKSPACE` 取得已选工作区，复用原登记、Score、媒体指针与专业 Stage；不启动后端或调度任务。
