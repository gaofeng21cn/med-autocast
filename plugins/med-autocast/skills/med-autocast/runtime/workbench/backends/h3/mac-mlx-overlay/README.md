# Mac MLX overlay

本目录保存本工作台在真实 M4 Max 上完成 MP4 验收的最小代码增量，应用目标是：

- 上游：`https://github.com/yshenaw/ComfyUI-MiniMax-H3-MLX-SolAttn.git`
- 固定基线：`55bb7ddd015321a25385683419951e7c7f518775`
- performance：resident + 单阶段 Qwen8，并在同一 runner 中复用 Qwen、DiT、Video VAE 和 Audio VAE
- 36GB compatibility：显式 `stream2` + `offset`，不继承 resident 内存承诺

`../setup_mac_local.sh` 会核对上游地址和 commit 后调用 `../apply_mac_mlx_overlay.sh`。应用脚本只接受干净基线或已经完整应用的同一 overlay；发现其他未提交改动会停止，避免覆盖第三方工作。

这里是运行实现，不是模型权重。权重位置仍由目标机器决定，且不应提交到工作台。
