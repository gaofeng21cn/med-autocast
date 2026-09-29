# Canvas 纸剧场基础模块

新集使用 [纸剧场模块](../paper_theatre/README.md)，支持独立镜头、连接点、共同事件和版本对照。本目录保留旧片兼容，不自动覆盖已有作品。

这里复用绘图能力，不提供固定镜头或疾病故事。新集从本目录复制 `paper_motion.js`、`paper_stage.js`，按顺序加载后再加载单集脚本。已存在的单集继续持有自己的版本，不自动覆盖。

- `PaperMotion`：纯时间进度 `move(time,start,duration)`、数值插值 `between(from,to,progress)`、限定时间窗口 `windowed(time,enter,leave,duration)`。
- `PaperStage.create(context)`：加载透明图片、纸片边缘、接触阴影、文字、矩形裁切和镜头变换。绘图同时记录当前变换后的主体、文字范围，供布局定位。
- 单集脚本：医学含义、纸件身份、事件、坐标、层级、切点、品牌档案和声段。不能从通用模块推导故事，也不复制样片的八镜顺序。

`await stage.load({name:'assets/item.png'})` 后才能 seek。每帧先 `stage.reset()`，再按导演稿绘制，输出 `window.__layout={subtitle:字幕范围,...stage.layout()}`。字幕绘制可暂用 `stage.track(false)`；结束后恢复。项目提供 `window.__seek(t)`、`window.__cuts`、`window.__total`、`window.__ready`，使用工作台已有预览/编码入口。

默认绘图坐标参考 1280×720；不同画幅须重排构图。主体范围按 alpha 非空区域计算，旋转后采用轴对齐包络；裁切也只给出包络，不能证明文字互不遮挡或语义成立。画外入场可以设计，但关键动作和阅读落点必须回到可见区域。阴影、局部椭圆裁切及直接 context 绘图仍由单集负责；必要时调用 `stage.bounds` 补充登记。

垂体瘤 v15 的实际返修说明：未使用且表现不可信的翻页不要塞入通用模块；裁切属于舞台，不同时在时间模块导出同名 API。固定件需要真实接触点，遮挡应发生在被解释物内部；标签须独立排版，不能靠大底纸解决构图。模板不包含品牌、医学资产、旁白或批准状态。模块可运行与艺术/医学验收分开。
