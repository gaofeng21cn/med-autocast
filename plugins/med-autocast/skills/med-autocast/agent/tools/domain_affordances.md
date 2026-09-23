# 工作台工具

完整工具职责、参数转交、运行环境和副作用见 [工具接入](../../docs/workspace-adapter.md)。先调用 med_autocast.py tools 读取确定的工具位置；workbench_tool.py 在明确 workspace_root 下同步执行原工具，优先工作区版本，缺少时使用随包核心。框架拥有阶段执行，领域工具只完成当前已授权操作。

inspect、assets、tools、preflight-workbench 只读；生成、合成、打包及产生检查文件的原工具均有相应副作用。媒体后端、作者授权资产、模型和凭据由工作区登记，不随包复制。专用审看包器仍由该工作区持有，使用前核对当前修订合同。
