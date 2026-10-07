---
name: medical-video-animation-craft
description: 把医学视频导演稿落实为可控的本地代码动画，选择媒介技法，打磨路径、镜头、材质、事件声音和可复用动作。用于 JavaScript/TypeScript 镜头实现与局部返修。
---

# 医学代码动画制作

先消费当前导演稿、可用素材、实际声段与本集 score；故事、医学事实与作者基线由原职责持有。实现支持导演意图，不让模块库存决定故事。默认是 Canvas 手绘拼贴纸剧场，renderer 与风格分别选择；视频模型仍只在用户显式选择时使用。

读 [代码动画技法与风格工作流](../../../runtime/workbench/docs/26_代码动画技法与风格工作流.md)，按本次选定风格加载 [风格目录](../../../runtime/workbench/templates/animation/styles/index.json) 中的 STYLE.md。它说明材质、动作、镜头、声音与失败模式；样例故事只用于看技法。新风格允许自由设计，现有七种研究不代表穷尽风格或医学生产资格。

先把一个最有解释力的镜头做成真实风格帧与短动作，现场看原尺寸，再逐镜扩展。路径绘制用 `kit/paths.ts` 的 measurePath/trace/pointAt，镜头/物件轨道用 `kit/tracks.ts`；接触后的 settle 衰减到静止。纸材、透明叠色、网点和固定件用 `kit/materials.ts`，或直接自定义 Canvas。对象可以 on-twos，镜头和声音保留主时钟；不为风格感持续抖动所有层。

构图由实际物件内容、认知主次与空间关系控制。PNG 透明外框和 bounds 帮助排除留白，不能自动决定物件大小。图层遮挡由容器/舞台局部层控制，接触点由素材登记或审定路径给出；医学生物结构不可由通用植物样例或自动生成路径代替。

画面与声音共用 `score.json`：重要接触、揭示和落点用命名事件驱动。声音调色板供导演选材，注册声音资产优先于程序合成音；合成音只是可运行的试作下限。允许静默与有目的的 J/L cut，不要求所有动作响。旁白沿用授权本地声线，动画工具不改 IndexTTS/Edge 策略。

通过 [工作台入口](../../../docs/workspace-adapter.md) 的 `animation_lab list` 查风格；`animation_lab create --project <新目录> --complete` 生成独立原创样片、源码、无旁白音效轨、帧、strip 和 MP4。用于学习与验证，不能覆盖真实单集或作者配置。实际单集沿用 `paper_project` 做局部预览/正式渲染，随机 seek、预览和编码必须同源。

审片顺序按问题选择：首帧与关键接触、完整动作、邻镜、正常速度整片与去文字。preview 的 text_observations 和 layout_findings 是定位线索；字体、背景对比、画面含义、阅读节奏与完整听感仍由 Review 判断。字段缺失或风格不理想记质量债并继续可消费工作，不让脚本替艺术审判。

有价值的模块连同冻结源码、依赖版本、score 事件、可看样例、适用与失败条件交素材策展保存；样例通过不能自动批准另一集。实际素材、个人声线和成片保留在工作区。外部方法 provenance 在风格目录 SOURCE.md；复制第三方代码/素材时另保留逐件许可。
