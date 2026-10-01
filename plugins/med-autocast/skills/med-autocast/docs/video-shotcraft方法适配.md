# Video Shotcraft 方法适配

更新：2026-10-01

本文把 GitHub `Vincentwei1021/video-shotcraft` 中可迁移的制作经验接入 Med Auto Cast。它是导演、分镜、动画和审片的组织方法，不是把该项目的品牌、素材、Remotion 依赖或产品宣传片语义搬入医学工作流。

## 适配范围

Shotcraft 最有价值的部分是“先设计镜头，再实现镜头”的工作节奏：用镜头配方卡交接意图，用一个主运动承担注意力，让运动经过准备、动作、反应、落定和停留，再用静帧、连续动作条、邻镜和整片多轮审查。声音也按旁白、音乐、拟音和转场的职责拆开；预览与正式渲染共享同一时间事实，seed 和时间函数可复现。

Med Auto Cast 的默认纸剧场路线将这些方法翻译为自然语言导演材料与本地 Canvas/TypeScript 实现：

- `shot_recipe` 是导演交接卡，不是强制 DSL。推荐写清患者读取任务、视觉锚点、主运动、动作弧、镜头与纸层、字幕安全区、声音事件、承接物和已知风险。
- 每镜先确定一个主焦点和一个主运动。环境可以呼吸，但不能靠持续抖动、悬空线段、色带或标签堆叠填时长。
- `prepare -> action -> reaction -> settle -> hold/rest` 是检查动作是否有因果和理解时间的参考弧。单集可改变节奏、阶段数量和具体动作。
- 首帧、准备姿态、动作极值、接触/落点、hold、切出帧先在代码预览中检查；12 姿态 strip、邻镜窗口和联系表用于定位，不能替代正常速度的连续观看。
- BGM、旁白、拟音和转场保持独立职责。正式交付从同一时间线导出带 BGM 和无 BGM（保留必要拟音）的版本；没有合法音乐时先交付无音乐候选，不阻断其他工作。
- 固定 seed、显式时间和 `window.__seek(t)` 保证预览与编码可复现。禁止用 `Date.now()`、跨帧累加状态或不可追溯随机数制造手工感。

## 与医学纸剧场的边界

Remotion、HyperFrames 或其他工具可以作为分镜/预览或替换渲染器，但不是纸剧场的默认后端。当前默认仍是本地 JavaScript + Canvas 2D；SVG、Remotion/DOM 和 Three.js/WebGL 按风格与镜头需要选择。所有后端共享 Score、Shot、Asset、Layout 和 Review 的语义，不把某个框架写成医学质量证明。

Shotcraft 的产品宣传片案例不能替代医学证据、素材许可、作者档案、声线授权或医生终审。`Dr.咩`、人物母版、IndexTTS 参考声线和系列固定印记只从目标工作区的作者/系列档案读取，通用 Skill 不内置品牌。用户可以显式跳过人物或专用声线；Edge TTS 只是无专用声线时的本地保底。

## Progress First

配方卡字段不完整、字幕尚未重排、双版本尚未导出或某个 strip 尚未生成时，保留已存在的候选和诊断，继续不依赖该缺口的素材、脚本、声音和审片工作。把问题记录为 `quality_debt` 或 `route_back`，由下游模型消费。只有权限、身份、当前版本、执行器不可用、被拒医学素材仍在使用或不可逆发布授权缺失时才硬停；技术检查不能伪造医学、完整听感或公开发布批准。

## 当前垂体瘤全季的应用

2026-10-01 全季审查覆盖 12 集当前技术候选、总时长约 773.902 秒。机器结果定位到：02 集有 12 帧、35 条主体/字幕包络重叠；02—11 各有 5 条超过 26 个非空字符的长字幕；02—11 与 E00 仍有泛化事件名；05、06、08、09 存在多个发布修订，01 同时保留 v19/v20。优先回导演稿重排 02—04 的空间与主动作，再重排字幕安全区、补真实语义事件、选择 current 发布目录并导出双声音版本。所有 manifest 仍保持 `release_eligible=false`，连续动态、完整听感和医学终审需独立完成。

审查入口：

```bash
node scripts/audit_pituitary_season.mjs
```

工作台报告在 `work/pituitary-paper-season/season-review-20261001.md`，JSON 用于后续复盘和版本对照，不作为发布门。

## 来源

- [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft)：`references/pipeline.md`、`aesthetic-rules.md`、`music-beat-sync.md`、`sound-design.md`、`final-review.md`、`workbench.md`，读取日期 2026-10-01。
- [video-talkcraft](https://github.com/Vincentwei1021/video-talkcraft)：词级时码、反幻灯片镜头系统和双轨交付方法，读取日期 2026-10-01。

外部项目只提供方法启发；Med Auto Cast 的实际状态以工作区文件、Stage 回执、作者/系列档案和独立 Review 证据为准。
