# 阶段任务

默认媒体制作路线：先确定作者/医生形象和声音基线；本地 JavaScript 动画负责可复现画面，作者有授权声线时使用本机 IndexTTS，Edge TTS 负责未设专用声线或用户主动跳过时的中文旁白；H3/Seedance 保留为显式备选。

各阶段目标与交接提示，常规 Stage 的质量角色受 OPL 阶段控制，不产生第二调度器。阶段能力包只提供输入/输出、工具和 route-back 的建议定位；它不是结构化 DSL，模型可以携带未列出的可消费材料继续推进。`meta-review.md` 是 `cross_stage_meta_review` 单次跨阶段总审阅，不递归启动另一轮 formal review。
