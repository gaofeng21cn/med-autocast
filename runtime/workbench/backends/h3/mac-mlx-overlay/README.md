# Mac MLX overlay

本目录保存应用到固定上游 commit 的最小代码增量，历史实测不能代替当前部署验证。当前随包 overlay 仅包含节点实现文件，不含 ComfyUI API workflow：

- 上游：`https://github.com/yshenaw/ComfyUI-MiniMax-H3-MLX-SolAttn.git`
- 固定基线：`55bb7ddd015321a25385683419951e7c7f518775`
- 需要提供与当前节点输入相符的 ComfyUI API workflow，并显式设置 MLX 内存/采样参数
- 36GB 内存路线需使用 `stream2`；该档位不会由 ComfyUI 启动脚本自动选择

`../setup_mac_local.sh` 会核对上游地址和 commit 后调用 `../apply_mac_mlx_overlay.sh`。应用脚本只更新本目录实际携带的两个节点文件；如果上游工作树有其他改动，不会覆盖它们。

这里是运行实现，不是模型权重。权重位置仍由目标机器决定，且不应提交到工作台。
