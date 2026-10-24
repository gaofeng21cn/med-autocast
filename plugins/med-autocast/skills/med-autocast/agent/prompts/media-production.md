# 媒体制作与剪辑

依据观看任务安排主焦点、支持组和背景；复杂核心用近景或拆解，小图采用简单轮廓或已解释归档图。完整人物替换后共同重排椅面、投影、接触层与道具，不沿用旧纸偶原点或残留手片；在原尺寸、手机宽预览、动作极值与邻镜中复核。方法见 `runtime/workbench/docs/44_人物素材与画面尺度契约.md`。

正式写动画前运行 `scripts/first_draft_preflight.py --project <单集工程> --pretty`，读取人物/姿态标尺、复杂对象尺寸和动画参考接线的定位报告；报告只生成候选与质量债，不把机器检查当视觉、听感、医学或发布通过。

纯视觉或说明返修可用 `mix --reuse-from-project <来源工程>` 核对真实声音依赖后保留原混音字节；保留来源工程或仅含明确音频输入的快照。声音依赖变化时重新混音，不由说明文字变化推断声音需要重做。

人物 `use` 后回读 `registration_readback` 与本集manifest的bounds/anchors，再按实际可见手、坐面和地面基准试装。精确修订必须能按含载荷描述的原记录合同重建；复制成功不批准姿态与接触。复杂结构小到读不清时换近景、拆解或简化资产。

画内文字先确定纸上排版/独立题注，使用同局部变换和明确宽高；固定件、笔尖及封面留阅读空间。先看真实帧与进入路径，别用加底板或缩字掩盖构图错误。方法见随包工作台 docs/37_纸片文字对齐SOP.md。

新增纸上文字使用 `Stage.label`/`textBox` 的显式安全区，`Stage.text` 仅为绘字底层。旧项目可先用 `audit_label_contract` 定位绕过区域的调用，再看真实镜头逐处迁移；不批量猜纸件归属。普通正式预览必须保留标签与字幕，`--clean` 仅辅助表意审查。

主要人物通过 `Stage.image`/本集 `img` 使用完整人物或完整姿态资产。程序绘制只补局部手部、袖口、附件或非叙事小图标，不能用 `oval`、`tornEllipse`、`poly`、`cutout` 临时拼患者、家属、医生、儿童、老人或孕妇。实际源码不得硬编码通用医生 ID 绕过作者解析：当前作者档案启用 `default_for_clinician` 时，无论医生身份或性别、是否显式 `generic`、是否给出精确外库 ID，都导入作者私有姿态；本机当前作者为 Dr.咩 时直接用 Dr.咩。第二名医生仅在导演稿明确是独立角色时使用对应专属完整素材。预览须核对图片实际加载路径和当前身份，不只看 manifest 是否登记。当前中景看脸、手、脚和接触；复杂结构缩到读不清时改近景/拆分，不靠标签。`audit_character_and_scale_contract.py` 仅给待审定位。

新视频默认使用本地 JavaScript/SVG/Canvas 动画：由确定性时间轴和 `window.__seek(t)` 驱动，Playwright 固定帧率捕获，FFmpeg 与最终旁白合成。先检索有明确操作能力的独立纸件、分层包与后景；关键帧只供导演参考。缺口按动作需要分别生成部件，或使用授权网上素材并记录来源。MiniMax H3 等视频模型只有在制作单明确选择时才调用。开始生产前先冻结作者/医生形象、是否露脸、授权参考音频和稳定表达方向；旁白优先用户授权声线或作者档案登记的本机 VoxCPM2，未提供声线或用户明确选择跳过专用声线时才使用 Edge TTS `zh-CN-XiaoyiNeural` 作为本地保底。

默认艺术风格为有叙事感的手绘拼贴。使用素材前先实际查看并登记；`check_animation_assets` 是素材状态与证据检查，不是整个制作阶段的启动门。被拒绝的素材必须从当前画面和渲染引用中排除；若医学主体缺失或无安全替代，先省略受影响镜头或改用已核实的表达，记录具体质量债和诊断回执，再继续不依赖该素材的镜头、声音、剪辑或 Review。不得用代码臆造未经核实的解剖。Pending 素材只可进入明确标记的审看候选，不得升格为通过、ready 或发布。ImageGen 通过当前会话的 ImageGen Skill 内置工具调用，生成后回写提示、回执和审核；Python 入口只检查登记，不声称提供图像生成模型。

执行时以当前单集 `score.json` 的 `styleId` 和 `renderer` 为请求来源；workflow 或作者档案中的选择应通过 `paper_project` 的 `init` 或 `adopt` 子命令传入 `--style-id ID --renderer ID`，不写回全局作者档案。后端未激活但页面可 seek 时生成审看候选，并在回执列出请求/实际 renderer 与 `quality_debt`；不得把请求 metadata 冒充运行结果。视觉风格实现由明确的 `appliedStyleId` 和导演/视觉 Review 共同确认，代码不得给语义质量签字。

品牌标记、医生形象和声线是默认首步。已有系列沿用作者档案的固定品牌露出、人物母版和声线；单集人物是否出镜由故事决定，仅用品牌标记也仍属于原系列，不记为跳过人物基线。只有用户明确放弃人物基线时才记录跳过。每集先写 `episode_blueprint`、beat grid、读取顺序和可分层透明素材计划，再写动画；编码前调用 `render_javascript_animation --preview --review-candidate` 看关键姿态、动作 strip、切点、联系表、layout 和字幕避让，返修后才导出 MP4。质量下限与迭代循环见 `runtime/workbench/docs/16_纸剧场前置策划与质量门.md`。

逐镜实现按本集导演 `shot_recipe` 交接对象、关系、变化或稳定状态。操作/接触镜头可用 `prepare -> action -> reaction -> settle -> hold/rest` 检查因果和理解时间；静态科学关系、揭示、局部变化和生活情境按解释任务实现，不硬套动作链、动作数量、前景视差或运镜。先保证基本意思成立，再打磨表现力。预览与正式编码使用同一 score、显式时间和 seek；固定 seed 允许复现手工纹理，但不能用随机抖动补足缺失的视觉事件。沿用同一旁白时间线导出带 BGM 与无 BGM（保留必要拟音）候选，分别记录音乐来源和混音状态。

全篇共用一个配音基线；禁止分场景改变情绪指令。Edge 使用 `render_edge_tts` 整篇合成及响度归一化，VoxCPM2 保持同一参考声线和全篇风格指令。使用 `audio_baseline` 定位音量异常，完整听感和语气一致性单独审查。声学通过不能把突然兴奋、角色变化或机械感标为通过。新的音轨必须重新校对时间轴。段首少字沿配音输入 → 源 take → 拼接轨 → 归一化轨 → mix → MP4 解复用音轨定位，逐段核对首词、尾词与接缝；区分漏读、截字/位移、采样率误用、混音遮盖和旧轨引用。默认保留原 take 解码样本，真实重采样，不以静音阈值裁掉弱辅音；时码来自实际采样。变化后 retime、build、mix、render，并检查用户会拿到的最终音轨，不强保旧时长。静音、能量、ASR 和波形指纹只是对应事实证据，不是听辨批准。

混音交接时重新计算当前旁白整轨和 `score.json` 的 SHA-256，并与 `mix-receipt.json` 的 `voice_sha256`/`score_sha256` 比较；任一失配即标记 `mix_lineage_mismatch`，重新 mix，并按新时长 retime、build、render。`source_timeline_bound` 或边界扫描通过不能替代最终 MP4 段首听辨；每段首词、接缝和结尾必须从用户实际拿到的 MP4 音轨中听辨并留证。未听辨的 `final_mp4_headword`/`full_listening` 保持 pending，旧 MP4、ASR、波形和静音报告不得冒充通过。

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

代码动画由 `medical-video-animation-craft` 按导演意图落实。复用 kit 的路径弧长、关键帧轨道、材质与接触动作，单集 score 仍是唯一时间事实；自定义绘制保留。先实现一个真实风格镜头，再扩展整片，音色选择与重要事件同步。`animation_lab` 是独立能力样例，不覆盖单集，不改变作者声线。方法见 `runtime/workbench/docs/26_代码动画技法与风格工作流.md`。

预览和正式渲染都自动运行 `audit_motion.py`，并保存 `medical_animation_runtime_receipt/v1`；动作审计的质量债不阻断候选，但必须随媒体交接传给 Visual Review，运行时回执用于确认本次代码、Score、素材、旁白和工具版本。

消费上游已注音的配音稿；启动推理前核对实际模型词表，记录请求 tts_text 与实际 model_text。独立返修只重配命中段，retime 保留字幕语义断句。调用已登记 audit_pronunciation 定位逐词覆盖及 build_no_music_mix 导出无BGM候选，不将机器定位当成发音通过。

可运动单件检查真实 alpha 与多底色边缘，区分假棋盘、全不透明背景、破洞及光晕；环境板可以不透明。源码、素材、Score/品牌变更后调用 paper_project build，再 preview 受影响窗口及邻镜，最后 render。回读本次 preview.json/实际帧和 out/current.json 指向的媒体及回执，退出码不证明画面或MP4已产生。模型词表先在首句/高风险整段小样验证，保留 tts_text/model_text；听辨仍单列。过期构建先修复，其他可消费工作继续，不沿用旧 bundle、不静默换声线。逐集看当前画面与同期旁白，代码统计只定位，不按分数决定合格或重写，代表集不替代其他集。每集保留问题时码、真实改变、修后候选和实际复核范围；已知表意或声音缺陷继续返修，不标 passed/ready 或混入用户最新版。方法见 `runtime/workbench/docs/39_逐集表意与段首完整性验收.md`。


独立 `mac-media-assets` 是默认发现入口。动画制作先用 native `assets --library external --animation-reference --query <动作或视觉锚点>` 得到按可运行动作、代码组件、分层部件和环境排序的候选，再实际查看 `resolved_payloads` 的原图/动作与本库 Skill。它只提供可复用下限，`creative_ceiling=open`；按本集故事决定复用、适配、另找合法素材或 ImageGen 新创，不设复用率，也不让已有素材决定故事、构图、风格、镜头数或新效果。库缺失、无匹配或旧素材不合适时继续新创与其他工作，质量债随交接保留。实际取用用 `media_asset_library use --project <单集路径> --id <精确外库ID>`；取用动作/代码包后检查项目 `animation_references[]`，再沿用工作台版本包与 uses，复制后当前镜头重新审查；作者范围仍按作者档案约束。安装/发现方法见 `docs/media-assets-integration.md`。

按中文对象、动作和叙事用途检索外库，使用 `collections` 查看装配与事件关系，查看真实小样后决定是否 `use-collection`。集合不固定故事与构图，欠项保留债务继续新创。部件bounds分别使用，不把单层总览当可配准分层。完整方法由资产策展Skill与随包 docs/32_资产发现与可重组事件SOP.md 提供。

### 长批次恢复与初稿证据

五小时级全季优化按单集保存 `retime/build/preview/mix/render/package` 回执和当前 Score/MP4 指针。中断后先读最近完整回执、当前 `out/current.json`、mix lineage 与 publish manifest，从最深未完成阶段继续；不重复生成已经绑定的旁白，不用旧目录或修改时间猜当前版本。第一次 animatic 后查看实际动作，再决定本集如何继续；resolve_motion_audit 仅只读汇集声明。按 runtime/workbench/docs/42_paper-collage-mv制作方法适配.md 先做道具各状态与局部完整小戏，用接触锚点、不同缓动和停顿落实导演；不靠字段/动作量清零扩展全季。
