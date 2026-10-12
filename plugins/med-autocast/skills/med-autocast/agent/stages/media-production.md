# 媒体制作与剪辑

先恢复原任务、精确输出与唯一写入者。读取部署 profile，复用音轨和已审源。按真实缺口执行已授权工作区后端入口、轮询原任务并验证输出；剪辑前预检当前制作单。

输入为当前请求、工作区配置和上一阶段可用结果。输出：精确媒体引用、去密回执、剪辑清单、候选成片。已有结果可直接进入本阶段，资料缺项记录为待处理问题；身份、权限与当前版本不一致时停止依赖该条件的动作。按任务语义决定前进或返修，不启动第二 writer。

专业入口：`agent/professional_skills/medical-video-backends/SKILL.md`。

代码动画按分镜制作完整纸面舞台与可表演的透明层，层序、接触和跨镜内容由镜头持有，素材锚点避免散落坐标。声音复用已授权基线，音乐可选合法曲库、明确许可的生成服务或原创本地采样器演奏；调用 `paper_project mix --music-plan` 混分轨，以实际旁白侧链压低配乐，音效引用画面命名事件。保留素材来源、音乐依据、混音与构建回执；缺音乐时先做无音乐候选，不阻断其他制作。通用 Skill 不固化品牌或乐曲。

制作消费导演配方卡而不是重新发明镜头语义：一个主运动先完成准备、动作、反应、落定和停留，再决定材质微动。固定时间与 seed 让 HTML 预览和 FFmpeg 编码一致；从同一时间线保留带 BGM/无 BGM 候选及其回执。

## 原工作台职责与专业交接

覆盖 S07—S08：配音与校对字幕、实际源片与区间、镜头排时、品牌和混音、唯一通用合成器及构建记录。

- `agent/professional_skills/medical-video-backends/SKILL.md`
- `agent/professional_skills/medical-video-director/SKILL.md`
- `agent/professional_skills/medical-video-visual-qa/SKILL.md`
- `agent/professional_skills/medical-video-release-packager/SKILL.md`

先读 `docs/production-sop.md` 的阶段映射；按 `docs/workspace-adapter.md` 选择实际工具和原输入合同。后续补充或返修从受影响职责继续，不为六阶段顺序重复制作。


中文旁白按完整语境确定多音字和医学术语读音。配音输入可用后端原生注音，字幕保留正文；先听首句与高风险词所在整段，局部重配同步时码并复核最终混音。普通中文 ASR 同字转写、注音输入成功与响度结果不能证明实际读音。当前 `audio/pronunciation-review.json` 是听辨索引，未覆盖听辨保持待审；已明确拒用的旧音不得复用。详见 `runtime/workbench/docs/27_中文配音发音控制与听辨SOP.md`。

分段配音按实测语音边界拼接，不按固定偏移首尾相接。TTS take 常带不等量前导静音，叠加设计停顿后每次切段都会吞掉首字——听感是“少了两个字”，而时长、响度与解码检查全部正常。用 `scan_narration_boundaries.py` 量每段 `head_silence`，用 `audio/narration_beats.json` 的 `splice.takes` 核对实际落点。修复只重新分配停顿以保持成片总时长；缩短音轨会让字幕与镜头失配，比原缺陷更严重。改了旁白依次重跑 retime、build、mix、render。详见 `runtime/workbench/docs/33_旁白拼接边界SOP.md`。

共享镜头工厂必须按主题安装系列视觉语法，让基础构图、景别、进入节奏和推移方向随疾病叙事而不同。推广工具只替换完整 `camera` 属性，备份放在 `work/series-grammar-backups/`，不得把备份留在 `src` 触发构建漂移；先单集 build/preview，再按系列推广。相机只提供下限，导演仍需为拿取、翻面、夹住、推入、折叠、打开和收纳设计纸件因果。详见 `runtime/workbench/docs/34_系列视觉语法与批量升级SOP.md`。

每个新单集必须先跑 `evaluate_episodes.py` 取得逐集诊断，再动手改写。评分低于 55 的集判为需重写，55–75 需升级，不允许凭观感批量重渲染代替逐集评估。镜头时序骨架统一用 `kit/patterns.ts` 的 `arc()`（进入→操作→反应→落定）、`unfoldRevealCompareStow()`、`walkArriveHandoff()`、`layerReveal()`；模式只管时序与姿态，画面由导演提供。逐集结论写入 `work/episode-optimization-report-<date>.md`，未完成的集必须显式标为待重写，不得计入已优化。

消费导演交来的语境注音与停顿意图，启动推理前将原生注音转换并核对实际模型词表；保存 tts_text/model_text。修订建立独立文件，重配只命中目标段；retime保留字幕语义断句，比例时码仍须复核。 方法见 `runtime/workbench/docs/28_初版质量与高效返修流程.md`。
