# 纸剧场制作模块 1.0.0

本地 TypeScript → Canvas → Chrome/FFmpeg。模块帮助稳定接触、遮挡、时间与预览，不固定故事、疾病、品牌、构图和动作风格。旧 `paper_canvas` 为历史片兼容入口，新集采用本目录。

## 可运行入口

`npm ci && npm run build`；直接打开 `index.html` 可观看无医学内容、无品牌的三个动作样本。开发时 `python3 -m http.server 8765 --bind 127.0.0.1` 后访问本地页面，可以检查 alpha 边界。`file://` 观看可运行，浏览器禁止读取本地图像像素时边界使用整图，不能据此判断精细避让。Node 22.18+ 或 24 用 `npm test` 执行动作边界测试。

样本可选择镜头、循环、逐帧、半速查看；默认不播放。`compare.html?before=before.mp4&after=after.mp4` 用相同秒数对照两个成片，默认静音，不以拉伸时间制造同步。

## 目录与职责

| 文件 | 唯一职责 |
|---|---|
| `src/kit/types.ts` | 素材、连接点、镜头、事件、画幅接口 |
| `src/kit/stage.ts` | 变换、裁切、纸材、图片与文字绘制、布局定位 |
| `src/kit/motion.ts` | 由时间直接求姿态，收纳弧线、盖章接触、事件定位 |
| `src/kit/props.ts` | 前袋遮挡、铰接、固定件；几何来自资产登记 |
| `src/kit/overlays.ts` | 参数化品牌印记、屏幕层字幕 |
| `src/kit/player.ts` | 整片装配、镜头选择、seek、逐帧、循环、速度与渲染公开入口 |
| `src/main.ts` | 无品牌动作样本；新集替换为单集装配 |
| `scripts/build.mjs` | 生成离线可运行的 `dist/film.js` |
| `scripts/mix_audio.py` | 从单集 `score.json` 的动作事件生成纸音并混音；不会调用 TTS |

## 新集接入

复制本模板，不复制 node_modules；安装锁定依赖。使用 `asset_manifest.json` 作为来源和绘图路径的同一入口，在单项的 `registration` 中登记 pivot、anchors 与可选 front 多边形（归一化图片坐标）。用 `score.json` 持有真实音轨时间、镜头边界、句级字幕和命名动作事件。`src/shots/<id>.ts` 持有逐镜构图、动作和相机；`src/main.ts` 只装配镜头。系列品牌从目标作者档案读取，单集快照注明原档案与基线。

一镜一个 `Shot`，`render({stage,t,beat,clean})` 中 `t` 为本镜秒数；`camera(ctx)` 可选。`stage.group` 使用物件局部坐标；前袋、连接点随父物件整体变换。字幕由播放器在镜头变换之外绘制。自定义镜头可以直接调用 `stage.g`；需要布局定位时使用 `stage.bounds`。不要把故事翻译成通用 JSON 动画 DSL。

声音引用 `{shot,event,kind,offset?}`，画面引用同一个事件时间，不在 Python 另抄百分比。混音示例：

```sh
python3 scripts/mix_audio.py --project . --voice audio/narration-normalized.wav --music assets/music.wav --output audio.wav
```

真实旁白使用统一 paper_project narrate/align/captions/mix 入口，完整听审独立进行。音轨变化后重新校准事件及镜头长度，不能简单整体拉伸每个动作。

## 动作使用条件

- pocket：登记前袋真实轮廓与 mouth，contents 在信封局部坐标绘制；素材不适合分层时更换素材，不拿矩形硬遮。
- stampPose：target 是接触位置，图片用 contact 锚点落地；printed 与声效引用同一 contact，轻重、幅度可以另写。
- hinge：平面纸件沿轴翻开；不冒充真实三维折纸。复杂透视需要专门镜头。
- onTwos：仅按需采样绘制姿态；禁止默认抖动医学解剖或字幕。

三个样本只演示机制。提炼新模块前，先在真实镜头中完成起点、过程、接触、结果和邻镜审看；保留自定义绘图出口。不要把参数合法、测试通过或边界不重叠说成艺术质量通过。

## 版本与验证

单集持有冻结 `src/kit` 与 package-lock.json；project.json 登记 kit_version，构建回执绑定实际源码，升级显式比较并重建，不用共享目录变更静默改变旧片。修正通用实现先回到本目录，再同步源码快照。播放器、预览和导出共用 `window.__seek(t_seconds)`；Canvas 入口声明实际 `__rendererId`，`__requestedStyleId` 保留制作单风格，只有 `__styleId` 明确声明已实现的风格。风格未声明或后端与制作单不一致时仍可生成候选，回执保留运行事实和质量债务；视觉是否符合所选风格仍由 Review 判断。

参考方法与本机落地取舍见工作台 `docs/19_纸剧场模块架构与镜头打磨.md`。本模块是独立实现，不复制第三方品牌与角色。

单集实际工具操作见[单集工具与局部返修](../../../docs/20_纸剧场单集工具与局部返修.md)。优先通过 init 复制全部入口和样本测试；纯动作样本可先无声预览，mix 后播放器接入实际音轨。
