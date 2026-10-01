# 故事与联合时间轴

先看已有资产与当前旁白，按整篇观看任务共同设计讲述与画面。为每段写可见事件、解释作用、入出镜承接与准确区间。

先读取当前工作区与目标选集的精确制作单。不要根据旧对话、文件前缀或mtime推断最新版。

提交可消费的故事包、分镜、旁白、镜头与复用/生成缺口清单，说明实际证据、欠项、下一阶段或返修点。判断标准：画面能否解释同期旁白；镜头承接是否清楚；跨集是否仅换名裁切；短片段是否造成碎镜。

从系列故事圣经写单集纸剧场分镜，注明物件含义变化、动作因果、景别、透明分层、读图停留和字幕空间。粗动态分镜及每镜 JS seek 预览可在最终编码前返修，首帧和切入帧须精确检查。

每镜附一张可读的 `shot_recipe`：患者先看什么、视觉锚点是什么、一个主运动如何经过准备/动作/反应/落定/停留、哪个物件接到下一镜、旁白/BGM/拟音各在何处服务。配方卡是导演交接和返修定位，不是必须满足的结构化启动条件；缺字段时保留故事包并记录质量债。

优先沿用用户在 workflow input 的 `style_selection`；没有显式选择时才读取系列作者档案和 `animation_style_registry.json` 默认值。把 `style_id`（艺术语言）和 `renderer`（实现后端）分开。未知风格先保留原请求、设计视觉处理并记录能力债务，不因目录不认识该值而退回默认风格或停止导演工作。

执行入口及质量边界见 `agent/professional_skills/medical-video-director/SKILL.md`、`agent/knowledge/domain_boundary.md`。

## 原工作台职责与专业交接

覆盖 S05—S06：内容与导演在正式配音前共同收敛整篇故事板和版本绑定的故事包；准备真实基础素材及替代。

- `agent/professional_skills/medical-video-content-planner/SKILL.md`
- `agent/professional_skills/medical-video-director/SKILL.md`
- `agent/professional_skills/medical-video-visual-qa/SKILL.md`

先读 `docs/production-sop.md` 的阶段映射；按 `docs/workspace-adapter.md` 选择实际工具和原输入合同。后续补充或返修从受影响职责继续，不为六阶段顺序重复制作。
