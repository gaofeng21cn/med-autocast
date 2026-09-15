# MiniMax H3 部署包

本目录同时保存 Linux/WSL2 + RTX 4090 的生产部署入口和 Apple Silicon 的本地备用入口。当前正式生产默认使用 RTX 4090；Mac 的 performance / 36gb 模式是独立可选能力，不会覆盖工作站配置。

## RTX 4090 固定组件

## 固定组件

- ComfyUI: `v0.34.0`
- Comfy-Org/MiniMax-H3: `4cc1d817b6184899b41293954329f576cb5ae86b`
- lightx2v/Minimax-h3-Turbo: `05ef678438e84933c406131b59abbf86919b3aac`
- FL2VA diffusion: INT8 pruned
- Text encoder: Qwen3-VL-32B NVFP4 AWQ
- Turbo LoRA: 8 steps

模型文件约 44.4 GB。安装、缓存和运行建议至少预留 70 GiB 可用磁盘、48 GiB 主机内存；当前原型使用 52 GB WSL2 内存配额。

## 运行

```bash
chmod +x setup_h3.sh run_h3.sh
./setup_h3.sh
./run_h3.sh
```

Mac 本地运行分为两个明确模式。当前高配 Mac 使用：

```bash
H3_MAC_MODE=performance ./run_h3_mac.sh
```

约 36GiB 统一内存的兼容机器使用：

```bash
H3_MAC_MODE=36gb ./run_h3_mac.sh
```

高性能模式加载 `minimax_h3_mlx_turbo4_sol.json`，显式 resident，并在同一 ComfyUI 进程内复用一套 Qwen、DiT 和 VAE。兼容模式加载 `minimax_h3_mlx_36gb_compat_turbo4_sol.json`，显式 stream2 + offset；两种模式不能混用内存承诺。

`setup_mac_local.sh` 会把关键 MLX 节点固定到已验收 commit，并应用 `mac-mlx-overlay/` 中的 resident 与 36GB 工作流实现。overlay 只覆盖该固定版本，目标仓库存在其他改动时会停止，避免静默覆盖。

国内网络下载 Hugging Face 模型较慢时，可临时使用镜像；模型 revision 仍由脚本固定：

```bash
HF_ENDPOINT=https://hf-mirror.com ./setup_h3.sh
```

在使用 systemd 的 WSL2 上，`run_h3.sh` 根据 `H3_ROOT` 渲染并启用用户服务，SSH 断开后服务仍持续运行。目录中的 service 是模板，不可直接复制安装。已有服务改变根路径时应显式停止旧服务后重新启动，不以修改源码替代运行时切换。

`pituitary_tumor_handdrawn_h3_v2`、两份旧人物图与对应提示是早期部署验证历史，不是当前制作模板或可分享的通用资产。当前作者母版只从工作台选定的作者档案读取；旧图片保留以复核已有制作单，不继续更新。部署脚本不再自动加载个人提示与图片，参考工作流需显式提供输入。正式字幕与品牌由通用合成器按作者档案叠加。

服务只监听 `127.0.0.1:8188`，应通过 SSH 端口转发访问，不要直接暴露到局域网或公网：

```bash
ssh -L 18188:127.0.0.1:8188 <workstation-lan-ssh-target>
```

`<workstation-lan-ssh-target>` 使用已经核验主机密钥的局域网 IP、mDNS 名称或 SSH 别名，不依赖 Tailscale。新镜头用 `scripts/queue_h3_shots.py` 通过配置的 ComfyUI API 排队，提示词和该后端参考图位置保存在对应 production 目录。第一集旧入口仅保留历史兼容，不用于新系列。

## 1-3 分钟视频的使用边界

H3 只负责短画面候选，IndexTTS 2.5 的最终音轨负责主时间轴。每个 H3 输出必须先检查再进入制作单：

- 关键解剖镜头传入已核对参考图，并在提示词中写清视图、定位标志、必须保持的位置和禁止位置。
- 报告、屏幕、药盒、胸牌等容易诱发伪文字；不能把字幕、品牌或报告字段交给 H3。
- 候选可以按 `source_start` / `source_end` 使用通过验收的区间，但错误已经污染核心医学对象时应整段重生成；关键关系可改用统一手绘风格的确定性信息动画，审定插图只能留作 animatic 或少量明确停留，不能替代整篇 H3 手绘动画。
- H3 后半段出现黑帧、身份漂移或额外头像时，即使前半段可用，也不得让错误区间进入最终时间轴。
- `Dr.咩` 头像使用 production 目录中的独立审定资产，H3 场景不得生成头像小窗，不从复合大图运行时裁切。

第一篇的机器可读示例见 `productions/01_mri_found_pituitary_lesion/production_plan.yaml`；最终合成统一由 `scripts/build_episode_video.py` 完成，旧单集路径只是转发入口。

完整的模块边界、制作方法、质量验收和后续迭代见 `../../docs/00_技术原型.md`。`make_limited_presenter_v3.sh` 只保留为“闭口静态人物仍会造成画外音违和”的历史实验，不是当前模板；现行品牌策略见 `../../docs/03_品牌人物呈现策略.md`。

## 范围与限制

- 这是开源 H3-Base 的本地 768p 以下验证路径，不含尚未开源的 H3-Context-IR 和 H3-Regenerate-2K。
- 工作流使用约 0.2 MP 画布降低 24 GB 显存上的验证成本；运行稳定后可在 Resolution Selector 中逐步提高到 0.4 MP 或官方 768p。
- 科普脚本只做一般健康教育，不提供诊断或治疗建议；生成后仍需人工检查解剖位置、字幕、语音和任何视觉伪影。
- MiniMax H3 Community License 排除美国、欧盟、英国和韩国；在这些地区运行、展示或分发需另行获得 MiniMax 授权。
