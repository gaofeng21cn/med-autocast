# 独立 MAC 媒体库接入

`mac-media-assets` 独立保管媒体、独立原记录、来源/审核边界与入口 Skill；MAC 持有工作流、作者档案和当前镜头审核。复用提高初稿下限，导演可适配、替换、网上找合法素材或 ImageGen 新创；不设复用率，不固定疾病故事、镜头数、构图或风格。

## 安装与发现

安装 MAC 工作台的标准命令是 `bash runtime/workbench/scripts/setup_workbench.sh --workspace <目录>`。它安装 Python 依赖后自动执行 `media_asset_library ensure`：先复用工作区配置、已安装伴随库或兄弟目录；缺失才从独立 GitHub 仓库克隆并校验。已有库不隐式 fetch、reset 或覆盖；部分目录有内容时保留并诊断。资产库不可访问、离线或校验失败不阻断新创。

仅完成 Codex 插件载体安装不会执行 shell，也不等于工作台及模型已经安装。工作台 setup 才是当前可执行的自动获取入口；`capability_dependencies` 声明 `optional_enhancement`，不能假称 OPL required closure 会安装一个可选依赖。资产库保持私有访问；使用已有 GitHub 身份授权，不写凭据、不把全部媒体塞进 MAC 或公开 OCI。

`workbench.yaml.asset_library.root` 是已有工作区的路径权威。没有可用默认路径时查找 `MAC_MEDIA_ASSETS_ROOT`、共享 companion 目录和已安装 Skill/插件；`CODEX_HOME`、`OPL_COMPANION_SOURCES_ROOT` 可指定宿主位置。自动创建的相对默认值不覆盖用户配置。`asset_library.enabled: false` 停用发现，`auto_install: false` 停用自动下载；手工已有库仍可只读使用。

## 制作的真实工具

```sh
python3 runtime/native_helpers/workbench_tool.py --workspace <目录> --name media_asset_library -- status
python3 runtime/native_helpers/workbench_tool.py --workspace <目录> --name media_asset_library -- ensure
python3 runtime/native_helpers/med_autocast.py assets --workspace <目录> --library external --query 纸景
python3 runtime/native_helpers/workbench_tool.py --workspace <目录> --name media_asset_library -- use --project productions/<系列>/<单集>/<版本> --id 'paper:<ID>@<REV>'
```

`status/query` 只读，不隐式下载或更新。查询返回真实原件绝对路径、动作样例和本库 Skill 入口；导演需看原件，判断其动作职责、比例、媒介与医学含义。查询为空也可继续导演工作和新创。

`use` 校验精确 ID、原记录、每个载荷哈希及作者范围；再接到已有 `animation_library.archive/reuse`，独立保管本地版本包、复制到项目并记录 uses 和 external-source。当前视觉/医学审核重新 pending，静态 `reference_only` 不导入运动素材清单。品牌、人物和声线不写死进通用 Skill。遇到不合适或缺证据的条目换材，不把拒用变成整个 Stage 的停止。

精选新创由策展阶段同步进独立库，保留源文件、许可/生成回执、内容边界、接触点、可看动作、适用与失败条件。库更新不自动替换旧片，文件校验不批准医学、艺术、动态或听感。
