# 独立 MAC 媒体库接入

`mac-media-assets` 独立保管媒体、独立原记录、来源/审核边界与入口 Skill；MAC 持有工作流、作者档案和当前镜头审核。复用提高初稿下限，导演可适配、替换、网上找合法素材或 ImageGen 新创；不设复用率，不固定疾病故事、镜头数、构图或风格。

## 安装与发现

标准安装 `opl packages install med-autocast --json` 由 OPL Framework 解析 required 依赖，先自动安装公开的 `mac-media-assets`，再安装 MAC；更新同样使用 Framework 的软件包入口。用户只执行一次 MAC 安装，不必单独安装素材 Skill 或手动克隆。资产库作为独立 headless 能力包，媒体与入口可由 MAC 调用，不占用普通对话的 Skill 入口。分发通过各自的 OCI 软件包，来源及版权证据随素材保存。

首次准备工作台使用 `bash scripts/setup_workbench.sh --workspace <目录>`。它调用 `media_asset_library ensure`，优先发现已安装的资产库；已有配置或兄弟目录仍可复用。缺失才从公开 GitHub 仓库获取并校验。已有库不隐式 fetch、reset 或覆盖；部分目录有内容时保留并诊断。直接使用原生 Codex 插件安装入口不会运行工作台 shell，也不会替代 Framework 的依赖安装入口。

安装依赖保证库自动到位；创作阶段仍 Progress First：离线、没有合适元素或素材欠项时可继续其他工作、找合法来源或 ImageGen 新创，不用素材匹配结果阻断故事与制作。已安装的媒体可离线查询和复制。

`workbench.yaml.asset_library.root` 是已有工作区的路径权威。没有可用默认路径时查找 `MAC_MEDIA_ASSETS_ROOT`、共享 companion 目录、OPL headless 原生载体及已安装 Skill/插件；`CODEX_HOME`、`OPL_COMPANION_SOURCES_ROOT` 可指定宿主位置。自动创建的相对默认值不覆盖用户配置。`asset_library.enabled: false` 停用发现，`auto_install: false` 停用自动下载；手工已有库仍可只读使用。

## 制作的真实工具

```sh
.venv/bin/python scripts/media_asset_library.py status --workspace .
.venv/bin/python scripts/media_asset_library.py ensure --workspace .
.venv/bin/python scripts/media_asset_library.py query --workspace . --query 纸景
.venv/bin/python scripts/media_asset_library.py character-coverage --workspace .
.venv/bin/python scripts/media_asset_library.py query --workspace . --character-role 老年男性 --pose walk
.venv/bin/python scripts/media_asset_library.py use --workspace . --project productions/<系列>/<单集>/<版本> --id 'paper:<ID>@<REV>'
```

`status/query` 只读，不隐式下载或更新。查询返回真实原件绝对路径、动作样例和本库 Skill 入口；导演需看原件，判断其动作职责、比例、媒介与医学含义。查询为空也可继续导演工作和新创。

默认检索每个资产身份返回一个当前版本，覆盖表保存精确 ID；`query --id <完整ID>` 回读指定版本，`--all-versions` 供追溯。`human_scale` 将设计身高与具体图像的尺寸、哈希和身体段标定绑定，形成原图像素/厘米；同场使用共同场景像素/厘米。`registration_readback` 核对锚点，`human_scale_readback` 核对项目注解完整复制，二者不批准真实比例或接触。按角色批填的身高仅为候选，标定 pending 不能当作已可自动排景；使用时不改不可变原包，精确版本注解随项目快照保留。详见[人物与尺度契约](44_人物素材与画面尺度契约.md)。

`use` 校验精确 ID、原记录、每个载荷哈希及作者范围；再接到已有 `animation_library.archive/reuse`，独立保管本地版本包、复制到项目并记录 uses 和 external-source。当前视觉/医学审核重新 pending，静态 `reference_only` 不导入运动素材清单。品牌、人物和声线不写死进通用 Skill。遇到不合适或缺证据的条目换材，不把拒用变成整个 Stage 的停止。

精选新创由策展阶段同步进独立库，保留源文件、许可/生成回执、内容边界、接触点、可看动作、适用与失败条件。库更新不自动替换旧片，文件校验不批准医学、艺术、动态或听感。

公开资产库只接收通用、无作者署名的媒体与组件。医生形象、授权声线、品牌参数、签名音乐和带品牌样片保管在私有作者工作区，不通过公共同步发布；发布前实际查看全部附带媒体。

分类、中文发现、可重组装配与事件取用已接入，参见 [资产发现与可重组事件 SOP](32_资产发现与可重组事件SOP.md)。新故事按对象、动作和叙事用途查库，先看实际小样；部件几何随版本独立记录，集合成员欠项不阻断其他工作。
