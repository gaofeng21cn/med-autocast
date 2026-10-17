# 媒体制作与剪辑

先恢复原任务、精确输出与唯一写入者。读取部署 profile，复用音轨和已审源。按真实缺口执行已授权工作区后端入口、轮询原任务并验证输出；剪辑前预检当前制作单。

输入为当前请求、工作区配置和上一阶段可用结果。输出：精确媒体引用、去密回执、剪辑清单、候选成片。已有结果可直接进入本阶段，资料缺项记录为待处理问题；身份、权限与当前版本不一致时停止依赖该条件的动作。按任务语义决定前进或返修，不启动第二 writer。

专业入口：`agent/professional_skills/medical-video-backends/SKILL.md`。

大批量声音返修先运行 `scripts/build_episode_review_queue.py`，再逐集沿源 take → 拼接轨 → 归一化轨 → mix → MP4 核对段首和接缝；队列只提供缺项与证据定位，不把元数据或批量退出码当作修复完成。

代码动画按分镜制作完整纸面舞台与可表演的透明层，层序、接触和跨镜内容由镜头持有，素材锚点避免散落坐标。声音复用已授权基线，音乐可选合法曲库、明确许可的生成服务或原创本地采样器演奏；调用 `paper_project mix --music-plan` 混分轨，以实际旁白侧链压低配乐，音效引用画面命名事件。保留素材来源、音乐依据、混音与构建回执；缺音乐时先做无音乐候选，不阻断其他制作。通用 Skill 不固化品牌或乐曲。

制作消费本集导演交接，先落实观众应看到的对象、关系、变化或稳定状态。有操作和接触的镜头核对准备、操作、反应、落定及理解停留；静态科学关系、生活情境、局部变化和揭示按各自解释任务实现，不套同一动作链，也不强制前景视差、动作数量或运镜。材质微动不能掩盖缺失的表意。固定时间与 seed 让 HTML 预览和 FFmpeg 编码一致；从同一时间线保留带 BGM/无 BGM 候选及其回执。

预览与正式渲染自动附带 `motion_audit` 和 `medical_animation_runtime_receipt/v1`；前者只报告导演质量债，后者绑定实际输入与工具，不把机器检查升级为成片通过。

## 原工作台职责与专业交接

覆盖 S07—S08：配音与校对字幕、实际源片与区间、镜头排时、品牌和混音、唯一通用合成器及构建记录。

- `agent/professional_skills/medical-video-backends/SKILL.md`
- `agent/professional_skills/medical-video-director/SKILL.md`
- `agent/professional_skills/medical-video-visual-qa/SKILL.md`
- `agent/professional_skills/medical-video-release-packager/SKILL.md`

先读 `docs/production-sop.md` 的阶段映射；按 `docs/workspace-adapter.md` 选择实际工具和原输入合同。后续补充或返修从受影响职责继续，不为六阶段顺序重复制作。


中文旁白按完整语境确定多音字和医学术语读音。配音输入可用后端原生注音，字幕保留正文；先听首句与高风险词所在整段，局部重配同步时码并复核最终混音。普通中文 ASR 同字转写、注音输入成功与响度结果不能证明实际读音。当前 `audio/pronunciation-review.json` 是听辨索引，未覆盖听辨保持待审；已明确拒用的旧音不得复用。详见 `runtime/workbench/docs/27_中文配音发音控制与听辨SOP.md`。

出现段首少字时，沿正文/配音输入、源 take、拼接旁白、归一化旁白、最终混音和 MP4 解复用音轨核对每段首词、尾词与接缝。区分源 take 漏读、拼接截字或位移、采样率误用、混音遮盖以及旧轨引用；前导静音、能量与 ASR 只定位，不直接归因为“静音吞字”。按实际采样率解码并真实重采样，默认保留源 take 样本及低能量辅音，时码来自实际写入的采样数。链路诊断、无 BGM 接缝和最终 MP4 的实际声音分别留证；实际漏读才局部重配，正确 take 复用。修复可能改变时长，应依次 retime、build、mix、render，不为保持旧时长截声或沿用旧时码。方法见 `runtime/workbench/docs/33_旁白拼接边界SOP.md` 与 `runtime/workbench/docs/39_逐集表意与段首完整性验收.md`。

每一集必须拥有自己的故事、导演稿、分镜和镜头实现；跨集只共享动画原语（kit）和纸件资产，不允许共享导演。系列级镜头工厂（six_shots/hypertension_shots/story_shots 之类）不是可选项，而是架构错误：它让同一系列每集用同样的空间、进入节奏和构图，把整个系列压成一份导演稿。每集新建 `episodeshots.ts` 与只含本集镜头的 `scene_directions.json`，可以 import 词汇层与 kit 原语（arc/place/contactShadow/paperRoom），禁止 import 其他集的镜头文件。可用 `scripts/check_episode_independence.py` 定位逐字复制，再核对实际故事、镜头和共用部分的职责；文件或哈希不同不证明导演独立，更不证明质量。共用故事工厂不能伪装成单集独立创作。背景板在渲染层由 `kit/rooms.ts` 的 `paperRoom()` 画成纸景房间（诊室/厨房/卧室/实验台/病房），不再用实景照片背景；`kit/staging.ts` 的 `paperPlate()` 负责把剩余图片背景拉进纸的媒介。详见 `runtime/workbench/docs/34_逐集独立导演与系列资产分层SOP.md`。

逐集返修先读本集导演稿、实际候选和上一轮 Review，明确应讲清的含义、画面实际表达和最早缺口，再决定保留、局部修复或重写镜头。`evaluate_episodes.py` 的代码统计只用于导航和定位可疑集，不按分数决定合格、重写或升级。`kit/patterns.ts` 的动作模式是可选实现工具，由本镜语义选择、调整或不用；跨集复用原语不复用导演。每集记录问题时码、实际改变、修后候选和真实复核范围；批量修工具、重渲染或代表集通过不能替代其他各集审片。已知表意或声音缺陷继续返修，不计为已完成，也不带 passed/ready 混入用户最新版。方法见 `runtime/workbench/docs/39_逐集表意与段首完整性验收.md`。

消费导演交来的语境注音与停顿意图，启动推理前将原生注音转换并核对实际模型词表；保存 tts_text/model_text。修订建立独立文件，重配只命中目标段；retime保留字幕语义断句，比例时码仍须复核。 方法见 `runtime/workbench/docs/28_初版质量与高效返修流程.md`。
