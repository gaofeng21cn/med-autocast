# 旁白拼接边界 SOP

段落切换听起来“少了头几个字”时，先定位最早发生变化的真实音频，不先归因为静音。源 take 可能漏读，拼接可能截字或错位，混音可能遮盖首词，当前视频也可能仍使用旧轨。前导静音会推迟起声，但静音本身不会删除词。能量阈值、频谱和 ASR 只用于定位，不能批准发音或授权裁掉低能量辅音。

## 范围与当前版本

从 `workbench.yaml` 的当前系列和单集登记、`project.json`、`out/current.json` 与交付 manifest 读取精确工程和媒体。修复只作用于当前目标集合，不遍历 `productions/*/*/v*`；工程副本和历史版本不能计为新增集数，也不能随当前修复批量改写。具体缺陷、数量和音频证据保存在工作区本轮报告，通用 SOP 不固化历史扫描计数。

## 沿声音链查实

对每段沿“审定正文/配音输入 → 源 take → 拼接旁白 → 归一化旁白 → 最终 mix → 当前 MP4 解复用音轨”比较首词、尾词、段长与接缝。分别保存无 BGM 和最终视频中包含完整短句的检查窗口；拼接回执写着 repaired、声轨时长正常或文件哈希更新，不证明首词完整可闻。

先核对源采样率、声道、解码采样数和实际时长。采样率转换必须真实重采样，不能把一种采样率的 PCM 按另一采样率直接解释。落位以实际写入采样数为准，不能只信 Score、ASR 或旧 splice 元数据。历史实现曾混用 IndexTTS 源 WAV 与目标采样率，必须通过真实媒体查出受影响工程，不把一次样本结论外推到全季。

`audit_narration_lineage.py` 对源 take、拼接/归一化整轨、mix 和视频音轨做波形指纹比对，定位 source_prefix_correlation、实际落位和元数据偏移。当前审计器使用 `narration_lineage_audit/v2`：以 `beat.start` 为中心建立局部 expected window，同时比较段首、段中、段尾多个波形锚点，并以联合分数和覆盖率判定位置；不会在整条长音轨中用偶然重复的短语冒充正确段落。它仍只证明特定信号在链路中的保留与位置，不证明词读对、整片听起来自然或音乐没有影响理解。

`mix-receipt.json` 的 `voice_sha256` 与 `score_sha256` 是当前混音输入的谱系声明。每次审查或打包前都要用实际读取的旁白整轨和 `score.json` 重新计算并比较；任一不一致都记录为 `mix_lineage_mismatch`，当前 mix 及其 MP4 不能作为修复后的声音证据，必须重新 mix，并按实际时长重新 build/render 后再回读。旧 mix、旧 MP4 和只更新 receipt 的报告可以保留作诊断，但不能用来填 `final_mp4_listening` 或发布状态。

`source_timeline_bound`/边界扫描通过只说明源段已经绑定到某个时间线，不说明最终文件听到了首词。每个语段都要从最终 MP4 解复用音轨中实际听辨段首，至少覆盖首词前后的完整短句和相邻接缝；无 BGM 轨与最终混音分别记录。最终 MP4 未实际听辨时，`final_mp4_headword` 与 `full_listening` 保持 `pending`，不得用源 take、ASR、波形指纹或静音报告代替。

## 修复方式

1. 源 take 已漏读或错读时，只重配该段，并拒用精确旧 take；未变且正确的声段继续复用。
2. 拼接读取或采样率处理有错时，修真实读取者。`narration_splice.py` 使用 FFmpeg 按源采样率解码并重采样至统一采样率，默认保留源 take 的全部解码样本；相对峰值裁切已废止，避免删弱首辅音。确需调整静音时先审实际边界，并保留必要余量。
3. 重新生成拼接轨、归一化轨和 receipt，写源路径/哈希、源采样率、保留采样数及实际 start/end。归一化不应改变语音时间线；发现变化先修音频链。
4. 真实新音轨时长可以与旧片不同。先按新声音 retime 字幕、镜头与事件，再 build、mix、render；不能以“保持旧总时长”为由删声、变速、均摊间隙或沿用旧时码。语义断句尽量保留，动作放不下时由导演重新编排。
5. 重新核对最终编码音轨、返修接缝与相邻切点；用户目录那份视频必须使用修复后的实际声音。完整听感、发音、动态和医学复核仍分开记录。

## 当前工具

先输出只读链路报告，可缩到单集：

```sh
python3 scripts/audit_narration_lineage.py --workspace <工作台> --series <系列ID> --episode <单集ID> --output <报告.json>
```

已确认拼接缺陷时，在外部备份目录保全当前声音、Score 与工程登记，再重建目标声轨：

```sh
python3 scripts/rebuild_narration_lossless.py --workspace <工作台> --series <系列ID> --episode <单集ID> --backup-root <备份目录> --manifest <修复回执.json> --apply
```

`rebuild_narration_lossless.py` 只修声轨和 receipt，状态是 `narration_ready_needs_retime_mix_render`；它不更新成片指针、不代表修后视频已完成。随后使用当前项目工具的 retime、build、mix、render，回读实际输出和交付版本。

`scan_narration_boundaries.py` 的 head_silence 可以找起声迟到的疑点；它不能证明丢字，也不能代替源 take 到视频的查实。旧按阈值裁头或按旧总时长配平的修复方式不用于新返修。

## Review 与交接

逐集核对所有声段首尾与接缝，并记录实际输入、源 take、当前混音/视频路径、检查方法、问题位置、修复和复核范围。没有实际听辨的范围保持 pending；波形保留、ASR 同字、响度和解码通过不能填 pronunciation/full_listening passed。

Review 看当前真实声音；Meta Review 核对声音与字幕、镜头、mix、MP4 是否同版，以及逐集覆盖是否完整。Progress First 保留候选和诊断，继续其他独立工作；已知缺字、错读、旧轨或遮蔽缺陷不能以 passed/ready 进入用户最新版。总方法见[逐集表意与段首完整性验收](39_逐集表意与段首完整性验收.md)。

修复或重新生成任一声段后，先运行 `scripts/audit_narration_samples.py --workspace <工作台> --output work/<本轮>/narration-samples.json`，检查源 take 是否完整落在原始 `audio/narration.wav` 的对应 PCM 窗口；再运行 `scripts/audit_audio_freshness.py --workspace <工作台> --output work/<本轮>/audio-freshness.json`，检查 source/timing/mix/render/publish 的实际 SHA 绑定。前者定位物理截字或错位，后者防止工程已修但用户仍拿旧 MP4；二者均不批准首字听清、发音、语气或完整听感。发现失配后按当前项目真实依赖重新执行 retime、build、mix、render、package 并回读；保留候选与诊断，其他独立工作继续，旧 MP4 不得作为用户最新版。
