# MiniMax H3 部署包

本目录保留 H3 的可选部署实现，包括标准 ComfyUI 与 MLX 兼容路线。工作台默认仍是本地 JavaScript 动画；H3 实例必须在制作单中显式选择，不能改变 `policy.default_video`。

MLX 兼容安装与运行脚本、固定版本 overlay 已随包保留；此目录不附带可直接生产的 MLX API workflow。部署档案只有在 workflow、模型和 MP4 回读都验证后，才能把相应实例标记为可调用；`media_backend doctor` 中服务可达只证明 ComfyUI 在线，不证明 workflow 可生成。

## 固定组件

- ComfyUI: `v0.34.0`
- Comfy-Org/MiniMax-H3: `4cc1d817b6184899b41293954329f576cb5ae86b`
- lightx2v/Minimax-h3-Turbo: `05ef678438e84933c406131b59abbf86919b3aac`
- FL2VA diffusion: INT8 pruned
- Text encoder: Qwen3-VL-32B NVFP4 AWQ
- Turbo LoRA: 8 steps

模型权重、缓存和运行资源按所选部署实例的诊断结果准备；这些要求不属于工作台核心安装条件。

## 标准 ComfyUI 运行

```bash
chmod +x setup_h3.sh run_h3.sh
./setup_h3.sh
./run_h3.sh
```

国内网络下载 Hugging Face 模型较慢时，可临时使用镜像；模型 revision 仍由脚本固定：

```bash
HF_ENDPOINT=https://hf-mirror.com ./setup_h3.sh
```

## MLX 兼容运行

```bash
./setup_mac_local.sh
./setup_mac_mlx_36gb.sh
./run_h3_mac.sh
```

模型下载和转换需先确认磁盘空间与适用许可。内存模式、采样配置由实际 API workflow 中的 MLX 节点参数决定；启动 ComfyUI 本身不会选择性能档。`apply_mac_mlx_overlay.sh` 只应用随包存在的节点实现文件，不会生成或伪装缺失的 workflow。生产调用须显式指定部署档案中的后端 ID 和已审 workflow。

若使用服务管理器，`run_h3.sh` 根据 `H3_ROOT` 渲染服务配置。目录中的 service 是模板，不可直接复制安装；已有服务改变根路径时应显式停止旧服务后重新启动，不以修改源码替代运行时切换。

旧工作流、人物图和提示只能作为各工作区的历史回执，不是当前制作模板或可分享的通用资产。当前作者母版只从工作台选定的作者档案读取；部署脚本不自动加载个人提示与图片，参考工作流需显式提供输入。正式字幕与品牌由通用合成器按作者档案叠加。

服务地址和安全访问方式由部署档案提供，不直接暴露到不受控网络。新镜头用 `scripts/queue_h3_shots.py` 通过档案解析的 ComfyUI API 排队，提示词和该后端参考图位置保存在对应 production 目录。

## 1-3 分钟视频的使用边界

H3 只负责短画面候选，VoxCPM2 的最终音轨负责主时间轴。每个 H3 输出必须先检查再进入制作单：

- 关键解剖镜头传入已核对参考图，并在提示词中写清视图、定位标志、必须保持的位置和禁止位置。
- 报告、屏幕、药盒、胸牌等容易诱发伪文字；不能把字幕、品牌或报告字段交给 H3。
- 候选可以按 `source_start` / `source_end` 使用通过验收的区间，但错误已经污染核心医学对象时应整段重生成；关键关系可改用统一手绘风格的确定性信息动画，审定插图只能留作 animatic 或少量明确停留，不能替代整篇 H3 手绘动画。
- H3 后半段出现黑帧、身份漂移或额外头像时，即使前半段可用，也不得让错误区间进入最终时间轴。
- `Dr.咩` 头像使用 production 目录中的独立审定资产，H3 场景不得生成头像小窗，不从复合大图运行时裁切。

第一篇的机器可读示例见 `productions/01_mri_found_pituitary_lesion/production_plan.yaml`；最终合成统一由 `scripts/build_episode_video.py` 完成，旧单集路径只是转发入口。

完整的模块边界、制作方法、质量验收和后续迭代见 `../../docs/00_技术原型.md`。`make_limited_presenter_v3.sh` 只保留为“闭口静态人物仍会造成画外音违和”的历史实验，不是当前模板；现行品牌策略见 `../../docs/03_品牌人物呈现策略.md`。

## 范围与限制

- 这是开源 H3-Base 的 768p 以下验证路径，不含尚未开源的 H3-Context-IR 和 H3-Regenerate-2K。
- 工作流可使用较小画布降低验证成本；稳定后再按部署实例的资源能力提高分辨率。
- 科普脚本只做一般健康教育，不提供诊断或治疗建议；生成后仍需人工检查解剖位置、字幕、语音和任何视觉伪影。
- MiniMax H3 Community License 排除美国、欧盟、英国和韩国；在这些地区运行、展示或分发需另行获得 MiniMax 授权。
