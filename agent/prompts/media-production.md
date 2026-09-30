# 媒体制作与剪辑

新视频默认使用本地 JavaScript/SVG/Canvas 动画：由确定性时间轴和 `window.__seek(t)` 驱动，Playwright 固定帧率捕获，FFmpeg 与最终旁白合成。先复用已审关键帧和插图，缺口再使用 ImageGen 或授权网上素材并记录来源。MiniMax H3 等视频模型只有在制作单明确选择时才调用。开始生产前先冻结作者/医生形象、是否露脸、授权参考音频和稳定表达方向；旁白优先用户授权声线或作者档案登记的本机 IndexTTS，未提供声线或用户明确选择跳过专用声线时才使用 Edge TTS `zh-CN-XiaoyiNeural` 作为本地保底。

默认艺术风格为有叙事感的手绘拼贴。使用素材前先实际查看并登记；`check_animation_assets` 是素材状态与证据检查，不是整个制作阶段的启动门。被拒绝的素材必须从当前画面和渲染引用中排除；若医学主体缺失或无安全替代，先省略受影响镜头或改用已核实的表达，记录具体质量债和诊断回执，再继续不依赖该素材的镜头、声音、剪辑或 Review。不得用代码臆造未经核实的解剖。Pending 素材只可进入明确标记的审看候选，不得升格为通过、ready 或发布。ImageGen 通过当前会话的 ImageGen Skill 内置工具调用，生成后回写提示、回执和审核；Python 入口只检查登记，不声称提供图像生成模型。

执行时以当前单集 `score.json` 的 `styleId` 和 `renderer` 为请求来源；workflow 或作者档案中的选择应通过 `paper_project` 的 `init` 或 `adopt` 子命令传入 `--style-id ID --renderer ID`，不写回全局作者档案。后端未激活但页面可 seek 时生成审看候选，并在回执列出请求/实际 renderer 与 `quality_debt`；不得把请求 metadata 冒充运行结果。视觉风格实现由明确的 `appliedStyleId` 和导演/视觉 Review 共同确认，代码不得给语义质量签字。

品牌标记、医生形象和声线是默认首步。已有系列沿用作者档案的固定品牌露出、人物母版和声线；单集人物是否出镜由故事决定，仅用品牌标记也仍属于原系列，不记为跳过人物基线。只有用户明确放弃人物基线时才记录跳过。每集先写 `episode_blueprint`、beat grid、读取顺序和可分层透明素材计划，再写动画；编码前调用 `render_javascript_animation --preview --review-candidate` 看关键姿态、动作 strip、切点、联系表、layout 和字幕避让，返修后才导出 MP4。质量下限与迭代循环见 `runtime/workbench/docs/16_纸剧场前置策划与质量门.md`。

全篇共用一个配音基线；禁止分场景改变情绪指令。Edge 使用 `render_edge_tts` 整篇合成及响度归一化，IndexTTS 保持同一参考声线和情绪参数。使用 `audio_baseline` 定位音量异常，完整听感和语气一致性单独审查。声学通过不能把突然兴奋、角色变化或机械感标为通过。新的音轨必须重新校对时间轴。

先恢复原任务、精确输出与唯一写入者。读取部署 profile，复用音轨和已审源。按真实缺口执行已授权工作区后端入口、轮询原任务并验证输出；剪辑前预检当前制作单。

先读取当前工作区与目标选集的精确制作单。不要根据旧对话、文件前缀或mtime推断最新版。

提交可消费的精确媒体引用、去密回执、剪辑清单、候选成片，说明实际证据、欠项、下一阶段或返修点。判断标准：输入是否为已审首帧和完整提示；任务预算是否累计；拒用源是否排除；旁白未变是否复用；媒体是否实际解码。

执行入口及质量边界见 `agent/professional_skills/medical-video-backends/SKILL.md`、`agent/knowledge/domain_boundary.md`。

## 原工作台职责与专业交接

覆盖 S07—S08：配音与校对字幕、实际源片与区间、镜头排时、品牌和混音、唯一通用合成器及构建记录。

- `agent/professional_skills/medical-video-backends/SKILL.md`
- `agent/professional_skills/medical-video-director/SKILL.md`
- `agent/professional_skills/medical-video-visual-qa/SKILL.md`
- `agent/professional_skills/medical-video-release-packager/SKILL.md`

先读 `docs/production-sop.md` 的阶段映射；按 `docs/workspace-adapter.md` 选择实际工具和原输入合同。后续补充或返修从受影响职责继续，不为六阶段顺序重复制作。
