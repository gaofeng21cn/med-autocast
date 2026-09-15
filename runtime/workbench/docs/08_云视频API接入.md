> 本文保留来源工作台的专业方法与制作案例。案例中的作者、疾病、路径、参数和实测状态不代表新工作区的默认或验收；当前任务以所选档案、制作单及真实证据为准。

# 云视频 API 接入合同

本文件负责工作台的云视频供应商协议、凭据边界和接入状态。协议定义登记在 `backends/config/media_backends.yaml`，用户的 endpoint、模型选择和实例 ID 登记在 `profiles/backends/<id>.yaml`；本文件不保存 API Key，也不把 OPL Gateway、某个供应商或某台机器设为所有部署的前置条件。

## 结论

- 云视频是工作台的一等后端能力，与局域网 RTX 4090、本地高性能 Mac 和本地 36GB 兼容模式并列存在，不替换任何现有后端。
- 在 OPL Gateway 原生支持某个视频协议以前，用户直接配置该供应商的 Base URL 和 API Key；工作台负责调用适配、异步轮询、下载、回执和技术验收。
- OPL Gateway 后续支持该协议时，只替换凭据和 endpoint 来源，不改变导演、视觉 QA、成片打包或其他后端合同。
- 不把“Bearer 鉴权”或模型出现在 `/models` 中等同于 OpenAI 协议兼容。每个供应商必须按真实创建、查询和下载接口分别适配。

## 责任边界

| 负责人 | 责任 |
| --- | --- |
| 用户/部署者 | 提供有权限和余额的供应商 API Key，确认区域、计费与内容政策 |
| 工作台后端适配器 | 参数转换、提交、轮询、下载、回执、错误归一化和媒体技术验收 |
| 供应商 | 模型、上游任务状态、计费和临时成片地址 |
| OPL Gateway | 未来可选的统一鉴权、路由和账务入口；当前不是云视频运行前提 |

凭据只允许来自环境变量或受控密钥存储，不写入项目 YAML、生产目录、回执、日志或 Skill。回执可以记录供应商、模型、任务 ID、请求参数、状态、耗时、输出哈希和供应商 request ID，但必须删除认证头和签名 URL 查询参数。

## 当前供应商登记

| 后端 | 当前状态 | 调用方式 | 说明 |
| --- | --- | --- | --- |
| `minimax_h3_api` | 协议已确认，调用器待实现 | 用户直连 MiniMax 官方 Video V2 API | 当前部署档案将其实例化为 `h3_official_api` |
| `seedance_2_5_api` | 协议已确认，调用器待实现 | 用户直连 APIYI 原生异步 API | 当前部署档案将其实例化为 `seedance_api` |

新增供应商前至少确认：稳定模型 ID、创建/查询/下载接口、认证方式、任务状态机、输入素材格式、输出 URL 生命周期、超时与限流、计费单位、内容政策和最小真实任务。缺少其中任何影响真实调用的合同，状态保持 `planned` 或 `contract_pending`。

## MiniMax 官方 H3 / H3 Max

截至 2026-09-04 已由 MiniMax 官方文档确认：

```text
Base URL：https://api.minimax.io
模型：MiniMax-H3 / MiniMax-H3-Max
创建：POST /v2/video_generation
查询：GET  /v2/query/video_generation/{task_id}
认证：Authorization: Bearer <MINIMAX_API_KEY>
状态：queued -> running -> succeeded | failed | cancelled
成片：task.content.url
```

这是 MiniMax 原生异步 Video V2 协议，不是 OpenAI Chat Completions、Responses 或 `/v1/videos`。用户启用时设置 `MINIMAX_VIDEO_API_BASE_URL` 和 `MINIMAX_API_KEY`；官方账号需要开通 Pay-as-you-go API。

两个模型共用创建与查询协议，但能力不同：

| 模型 | 输入模式 | 分辨率 | 时长 |
| --- | --- | --- | --- |
| `MiniMax-H3` | 文生、首/尾帧图生、参考图/视频/音频 | `768P` / `2K` | 4–15 秒整数 |
| `MiniMax-H3-Max` | 文生、首/尾帧图生；不支持参考输入 | `480P` / `768P` | 5–15 秒整数 |

最小文生视频请求：

```json
{
  "model": "MiniMax-H3",
  "content": [
    {
      "type": "text",
      "text": "医学手绘动画提示词"
    }
  ],
  "resolution": "768P",
  "duration": 5,
  "ratio": "16:9"
}
```

成功提交返回 `task_id`；轮询成功后立即下载 `task.content.url`。文生视频必须显式传非 `adaptive` 的 `ratio`；图生视频的比例由输入图决定；参考生成可以使用 `reference_image`、`reference_video`、`reference_audio` 角色，但不能与 `first_frame` / `last_frame` 混用。

官方创建接口当前没有登记独立的 `generate_audio` 开关，适配器不得把工作台同名字段盲传给供应商。正式剪辑使用 IndexTTS 时，应在下载后检查并按制作单处理模型音轨。

官方资料：

- [MiniMax H3 视频生成指南](https://platform.minimax.io/docs/guides/video-generation)
- [创建 Video V2 任务](https://platform.minimax.io/docs/api-reference/video-generation-v2-create)
- [查询 Video V2 任务](https://platform.minimax.io/docs/api-reference/video-generation-v2-query)
- [MiniMax 按量计费](https://platform.minimax.io/docs/guides/pricing-paygo#video)

## APIYI Seedance 2.5

截至 2026-09-04 已确认的官方模型与路由：

```text
模型：doubao-seedance-2-5-260628
APIYI Token 分组：SeeDance2
创建：POST https://api.apiyi.com/seedance/api/v3/contents/generations/tasks
查询：GET  https://api.apiyi.com/seedance/api/v3/contents/generations/tasks/{id}
认证：Authorization: Bearer <APIYI_KEY>
状态：queued -> running -> succeeded | failed | expired
成片：content.video_url，签名地址约 24 小时过期
```

最小文生视频请求：

```json
{
  "model": "doubao-seedance-2-5-260628",
  "content": [
    {
      "type": "text",
      "text": "医学手绘动画提示词"
    }
  ],
  "duration": 5,
  "resolution": "720p",
  "ratio": "16:9",
  "generate_audio": false,
  "watermark": false,
  "output_format": "mp4"
}
```

工作台已有 IndexTTS 旁白时间轴时，默认显式传 `generate_audio=false`，避免供应商另生音轨干扰剪辑。`duration` 也必须显式传递；Seedance 2.5 省略时可能由模型自行选择时长并改变费用。

建议首次轮询在提交后 20–30 秒开始，之后每 10–20 秒查询一次。成功后立即下载 `content.video_url` 并运行 `ffprobe`；不得把短期签名 URL 当作交付物。APIYI 请求可显式设置 `Accept-Encoding: identity`，避免部分客户端对压缩响应处理不一致。

工作台统一字段映射为：

| 工作台字段 | APIYI 字段 |
| --- | --- |
| `prompt` | `content[0].text` |
| `duration_seconds` | `duration` |
| `resolution` | `resolution` |
| `aspect_ratio` | `ratio` |
| `generate_audio` | `generate_audio` |
| `seed` | `seed` |
| `output_format` | `output_format` |

官方资料：

- [Seedance 2.0 / 2.5 概览](https://docs.apiyi.com/api-capabilities/seedance2/overview)
- [Seedance 视频生成接口](https://docs.apiyi.com/api-capabilities/seedance2/video-generation)
- [Seedance 2.5 与 2.0 统一分组](https://docs.apiyi.com/live/2026-08/seedance-2-5-group-merge)

## OPL Gateway 后续接入条件

当前 Sub2API `v0.2.0` 的 OpenAI Videos 路由只支持 Grok/xAI；模型映射和自动透传不会把 `/v1/videos` 转换为 MiniMax 的 `/v2/video_generation`，也不会转换为 APIYI 的 `/seedance/api/v3/...`。因此当前不把 OPL Gateway 写进 `h3_official_api` 或 `seedance_api` 的运行路径。

只有 OPL Gateway 对目标供应商真实提供创建、查询、下载、任务归属和一次性结算后，才把对应后端切换到 Gateway Base URL。验收必须使用 Gateway 用户 Key 完成一个最小真实视频并下载可解码成片；仅 `/models` 可见、配置保存成功或返回任务 ID 都不算支持。

## 后续适配器验收

每个云视频适配器至少完成一次 4–5 秒低分辨率真实任务，并保存去密后的生成回执。验收同时确认：

1. 提交参数与目标模型一致；
2. 轮询能够收敛到终态，失败信息可读；
3. 成片在签名地址过期前下载到用户指定目录；
4. `ffprobe` 能读取时长、分辨率和编码；
5. API 后端是显式选择，不会改写 `h3_remote_4090` 默认值；
6. 凭据、认证头和完整签名 URL 没有进入仓库或回执。
