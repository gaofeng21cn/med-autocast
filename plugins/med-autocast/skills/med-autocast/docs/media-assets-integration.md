# 独立 MAC 媒体库接入

`mac-media-assets` 独立保管媒体、独立原记录、来源/审核边界与入口 Skill；MAC 持有工作流、作者档案和当前镜头审核。复用提高初稿下限，导演可适配、替换、网上找合法素材或 ImageGen 新创；不设复用率，不固定疾病故事、镜头数、构图或风格。

## 安装与发现

标准安装 `opl packages install med-autocast --json` 由 OPL Framework 解析 required 依赖，先自动安装公开的 `mac-media-assets` 轻量目录包，再安装 MAC；更新同样使用 Framework 的软件包入口。用户只执行一次 MAC 安装，不必单独安装素材 Skill 或手动克隆。资产库作为独立 headless 能力包，媒体与入口可由 MAC 调用，不占用普通对话的 Skill 入口。分发通过各自的 OCI 软件包，来源及版权证据随素材保存。

所有 MAC 标准安装入口默认依赖轻量素材包；OPL App Full 也内置经内容锁校验的小核心。旧发行尚未携带小核心时，App 沿现有 Official Profile required 依赖补齐。同一素材库在软件中心提供“安装离线完整版”，用户主动选择后安装全部登记媒体；不另建产品条目。MAC 每次开始或恢复实际制作时运行 `python3 runtime/native_helpers/med_autocast.py prepare --workspace <目录>`，检查已安装库，缺失才安装并回读路径。单独 inspect/query 继续只读，用户停用自动下载的设置有效。

首次准备工作台使用 `bash runtime/workbench/scripts/setup_workbench.sh --workspace <目录>`。它调用 `media_asset_library ensure`，优先发现已安装的资产库；已有配置或兄弟目录仍可复用。缺失时优先通过 `opl packages install mac-media-assets --json` 交给 Framework 安装、配置并重新发现；不能只凭命令退出成功声明库可用。没有 Framework 的独立插件环境保留既有公开 GitHub 获取与校验路径。Framework 失败或超时只返回诊断，不再另起 Git 克隆重试。已有库不隐式 fetch、reset 或覆盖；部分目录有内容时保留并诊断。直接使用原生 Codex 插件安装入口不会运行工作台 shell，也不会替代 Framework 的依赖安装入口。

安装依赖保证库自动到位；创作阶段仍 Progress First：离线、没有合适元素或素材欠项时可继续其他工作、找合法来源或 ImageGen 新创，不用素材匹配结果阻断故事与制作。已安装的媒体可离线查询和复制。

`workbench.yaml.asset_library.root` 是已有工作区的路径权威。没有可用默认路径时查找 `MAC_MEDIA_ASSETS_ROOT`、共享 companion 目录、OPL headless 原生载体及已安装 Skill/插件；`CODEX_HOME`、`OPL_COMPANION_SOURCES_ROOT` 可指定宿主位置。自动创建的相对默认值不覆盖用户配置。`asset_library.enabled: false` 停用发现，`auto_install: false` 停用自动下载；手工已有库仍可只读使用。

## 制作的真实工具

新版库提供轻量目录与按需媒体，检索仍离线且只读；查询的 `storage.fetch_required` 表示所选原件尚未获取。`use` 才调用库内 `media_store fetch`，逐文件校验后沿原有 archive/reuse 复制。相同哈希共享缓存，项目副本独立。`asset_library` 可配置 `cache_root`、`cache_limit_bytes`、`auto_fetch` 和 `offline`；已有路径与作者设置不改写。独立获取优先部分克隆和稀疏检出元数据，旧完整库继续使用。发布与缓存细节由素材库的 `docs/media-storage.md` 持有。

新版查询还可组合 `--system <医学系统>`、`--topic <主题>`、`--patient-task <患者任务>`。未下载媒体不能宣称已经看过；先按所选精确版本取用或预取，再看真实原件和动作。

```sh
python3 runtime/native_helpers/workbench_tool.py --workspace <目录> --name media_asset_library -- status
python3 runtime/native_helpers/workbench_tool.py --workspace <目录> --name media_asset_library -- ensure
python3 runtime/native_helpers/med_autocast.py assets --workspace <目录> --library external --query 纸景
python3 runtime/native_helpers/med_autocast.py assets --workspace <目录> --library external --animation-reference --query <动作或视觉锚点>
python3 runtime/native_helpers/med_autocast.py assets --workspace <目录> --library external --character-role 老年男性 --pose walk
python3 runtime/native_helpers/workbench_tool.py --workspace <目录> --name media_asset_library -- character-coverage
python3 runtime/native_helpers/workbench_tool.py --workspace <目录> --name media_asset_library -- use --project productions/<系列>/<单集>/<版本> --id 'paper:<ID>@<REV>'
```

`status/query` 只读，不隐式下载或更新。查询返回真实原件绝对路径、动作样例和本库 Skill 入口；导演需看原件，判断其动作职责、比例、媒介与医学含义。查询为空也可继续导演工作和新创。

`--animation-reference` 是动画制作的快捷入口：按“可运行动作/代码组件 -> 可拆分部件 -> 人物/医学层 -> 环境”排序，返回精确版本 ID、`resolved_payloads`、动作样例与限制，并明确 `baseline_only=true`、`creative_ceiling=open`。它提高初稿下限和检索效率，不锁定故事、构图、风格或运动上限。MAC 可以直接适配候选，也可以跳过候选创作新素材、新动作和新渲染方法。

`use` 校验精确 ID、原记录、每个载荷哈希及作者范围；再接到已有 `animation_library.archive/reuse`，独立保管本地版本包、复制到项目并记录 uses 和 external-source。当前视觉/医学审核重新 pending，静态 `reference_only` 不导入运动素材清单。品牌、人物和声线不写死进通用 Skill。遇到不合适或缺证据的条目换材，不把拒用变成整个 Stage 的停止。

取用 `motion_recipe` 或 `code_component` 后，项目 `asset_manifest.json.animation_references[]` 会保存外部精确 ID、revision、本地入口、记录哈希、`mode=baseline_reference`、`creative_ceiling=open` 和当前镜头待审状态。`check_animation_assets` 会在渲染前回读这些入口和字节；这只证明调用链完整，不替代当前镜头的视觉、连续动态、医学或听感审查。

精选新创由策展阶段同步进独立库，保留源文件、许可/生成回执、内容边界、接触点、可看动作、适用与失败条件。库更新不自动替换旧片，文件校验不批准医学、艺术、动态或听感。

## 人物与批量写入边界

人物、椅面、投影和接触道具作为关系组试装；换完整人物、裁切或改变相机后共同调整落点。按本镜观看任务分主焦点、支持组与背景，复杂核心用近景或拆解，小图只保留简单轮廓或已解释归档内容。总览、解释近景与简化版分别查询和看原件；尚无审定版本时准备缺口。原尺寸、手机宽预览及动作极值/邻镜的判断方法见[人物素材与画面尺度契约](../runtime/workbench/docs/44_人物素材与画面尺度契约.md)。

人物覆盖表保存精确版本，默认检索每个身份返回一个当前候选；缺姿态先准备完整人物。`use` 成功后回读 `registration_readback` 与本集manifest的bounds/anchors，再在代表镜头中验证实际接触。锚点字段和复制成功不能代替原件部位与动作试装；版本号按包含实际载荷描述的原记录合同重建，旧修订保留恢复。

主要患者、家属、医生及儿童、老人、孕妇按[人物素材与画面尺度契约](../runtime/workbench/docs/44_人物素材与画面尺度契约.md)在剧本与分镜前准备完整人物或姿态，不能用圆头、梯形身体和独立四肢临时拼人。查询先用“青少年/儿童/老人/孕妇/医生/坐姿/步行/接取”等角色与动作同义词，再查看实际载荷和内容 bounds；导入后当前镜头仍需重审尺度、遮挡和接触。

`animation_library` 的资产包归档与项目取用分别使用跨进程锁和唯一临时文件。多个项目并行 `use` 同一素材时，不能共享固定的 `uses.json.tmp`，也不能竞争同一个 content-addressed 目标目录。批量完成后仍回读项目 manifest、实际载荷和 `uses.json`；锁只保护写入完整性，不批准素材或镜头质量。

## 精确版本撤回与审核修正

外挂库的 `collections/curation.json` 覆盖目录和原包的历史审核声明。查询、精确 ID 导入和组合取用均应用当前决定；`needs_rebuild` / `superseded` 不可导入，损坏的策展记录不静默回退。

导入保留原记录与原载荷，并在 `external-source.json` 保存 `effective_review_boundary`、当次策展和当前镜头 pending。本地缓存保存精确版本注解及外库来源根；直接重用时重新读取中央决定，防止导入后被撤回的包继续从缓存进入新项目。旧工程保持原版本，后续修订按受影响范围重新审查。

完整离线安装可保存直接使用的WebP/AAC/FLAC与去重媒体。`status/query/use` 发现与当前核心索引、内容锁匹配的离线安装后使用其压缩版本；旧ID按来源映射到新revision，保留独立扩展名、哈希、坐标和当前镜头待审状态。项目复制仍独立，缓存清理不删除项目文件。
