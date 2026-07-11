# 播客转视频（podcast-to-video）

一个把**播客音频**自动合成为**平台可发布视频**的 Codex 技能（skill）。它会把音频、方形封面/Logo、节目元信息和字幕组合成带波形动画、进度条和精准同步中文字幕的竖版 / 横版视频，适用于抖音、微信视频号、B 站、小红书、YouTube Shorts / Reels 等平台。

## 功能特性

- **双版式一键生成**
  - `vertical` 竖版 1080×1920，适配抖音、微信视频号、小红书、Shorts / Reels。
  - `horizontal` 横版 1920×1080，适配 B 站及长视频平台。
- **精美封面页**：模糊虚化封面背景 + 清晰封面、节目名、单集标题、嘉宾、主播、录制/发布日期、片段标签。
- **动态声音波形**与底部进度条。
- **中文字幕烧录**：基于 SRT 生成 ASS 字幕，自动断句、去重叠、合并短句，字号与安全边距按版式适配。
- **字幕纠错与净化**：支持人名/节目名/术语的替换纠错（`--correction`），并可过滤 ASR 在音乐、静音、片尾处产生的幻觉垃圾字幕（`--banned-fragment`）。
- **可选 ASR 兜底**：无 SRT 时可用 FFmpeg 的 `whisper` 滤镜 + whisper.cpp 模型自动生成字幕。
- **交付前质检**：自动截取关键帧截图，并对每个输出运行 `ffprobe`，同时生成 JSON 清单文件。

## 环境依赖

- **Python 3.10+**（代码使用了 `list[str]`、`str | Path` 等新式类型标注）。
- **Pillow（PIL）**：用于绘制封面页与文字排版。
  ```bash
  pip install -r requirements.txt
  ```
- **FFmpeg / ffprobe**：需已安装并加入系统 `PATH`，用于合成视频、生成波形、截图与探测参数。
- **中文字体**：Windows 的微软雅黑（msyh）、Noto Sans CJK 或 macOS 的 PingFang。缺失时中文会显示为方块。
- **（可选）whisper.cpp 的 ggml 模型**：仅在需要自动生成字幕时使用，例如 `ggml-large-v3-turbo-q5_0.bin`。

## 快速开始

将脚本从技能目录调用即可。最简单的方式是准备好音频、封面和字幕后运行：

```bash
python scripts/podcast_video.py \
  --audio "./episode.m4a" \
  --cover "./cover.png" \
  --srt "./episode.srt" \
  --podcast-name "苦中找乐" \
  --title "上职高的孩子什么样？在职高当老师有啥体验？" \
  --mode full
```

默认会同时生成竖版和横版视频。

## 命令行参数

| 参数 | 说明 |
| --- | --- |
| `--audio`（必填） | 原始高音质音频（`.m4a` / `.mp3` / `.wav`）。 |
| `--cover`（必填） | 单集封面或节目 Logo，建议方形、宽度 ≥1000px。 |
| `--srt` | 字幕 SRT 文件；除非提供 `--asr-model`，否则必填。 |
| `--asr-model` | 可选，whisper.cpp 的 ggml 模型路径，用于经 FFmpeg whisper 滤镜自动生成字幕。 |
| `--language` | ASR 语言，默认 `zh`。 |
| `--metadata-json` | 可选的 JSON 元信息文件（命令行参数会覆盖 JSON 中的同名字段）。 |
| `--podcast-name` / `--title` / `--episode-tag` / `--guest` / `--host` / `--recorded-at` / `--published-at` / `--segment-label` | 节目名、单集标题、单集标签、嘉宾、主播、录制日期、发布日期、片段标签。 |
| `--mode` | `sample`（样片，默认，约 75 秒）或 `full`（完整版）。 |
| `--start` | 音频起始偏移（秒）。 |
| `--duration` | 输出时长（秒）。 |
| `--stem` | 输出文件名主干。 |
| `--work-dir` | 中间文件目录，默认 `podcast_video_work`。 |
| `--output-dir` | 输出目录，默认 `podcast_video_outputs`。 |
| `--layout` | 可多次指定，取值 `vertical` / `horizontal`；不指定则两者都生成。 |
| `--correction` | 字幕纠错，形如 `杨航=羊行`，可多次使用。 |
| `--banned-fragment` | 丢弃包含该文本的字幕行，可多次使用。 |
| `--no-screenshots` | 不生成关键帧截图。 |

## 元信息 JSON 示例

```json
{
  "podcast_name": "苦中找乐",
  "title": "上职高的孩子什么样？在职高当老师有啥体验？",
  "episode_tag": "对谈 夜夜页页小马 - 093",
  "guest": "小马（夜夜页页主播）",
  "host": "羊行",
  "recorded_at": "2026年5月11日",
  "published_at": "2026年6月29日",
  "corrections": ["杨航=羊行", "博客=播客"],
  "banned_fragments": ["YoYo Television Series"]
}
```

> 命令行参数优先级高于 JSON 中的对应字段。

## 常用示例

**从 02:25 处生成 75 秒样片：**

```bash
python scripts/podcast_video.py \
  --audio "./episode.m4a" --cover "./cover.png" --srt "./episode.srt" \
  --podcast-name "节目名" --title "标题" \
  --start 145 --duration 75 --mode sample --stem "episode_sample"
```

**用元信息 JSON 生成完整版（双版式）：**

```bash
python scripts/podcast_video.py \
  --audio "./episode.m4a" --cover "./cover.png" --srt "./episode.srt" \
  --metadata-json "./metadata.json" --mode full --stem "episode_full"
```

**仅生成竖版：**

```bash
python scripts/podcast_video.py \
  --audio "./episode.m4a" --cover "./cover.png" --srt "./episode.srt" \
  --podcast-name "节目名" --title "标题" --layout vertical
```

**无 SRT 时用 whisper 模型自动生成字幕：**

```bash
python scripts/podcast_video.py \
  --audio "./episode.m4a" --cover "./cover.png" \
  --asr-model "./ggml-large-v3-turbo-q5_0.bin" \
  --podcast-name "节目名" --title "当期标题"
```

## 字幕（ASR）策略

优先级从高到低：

1. 官方或制作方提供的带时间轴 SRT / ASS / VTT。
2. 已登录来源导出的平台转写文本。
3. 带术语表的云端 ASR。
4. 本地 FFmpeg `whisper` 滤镜 + whisper.cpp 模型。

中文播客建议使用 `large-v3-turbo` 级别模型，质量通常明显优于小模型；务必配置人名、节目名、常用术语的纠错表，并重点检查片尾在音乐/静音后的幻觉字幕。

## 输出内容

运行后会得到：

- 竖版 / 横版 MP4 视频；
- 对应的 ASS 字幕文件与背景图 PNG；
- 关键帧截图（开头、中段、结尾附近）；
- 一个 `*_manifest.json` 清单，记录各版式的背景图、字幕、视频、截图路径及 `ffprobe` 探测结果。

## 交付前质检清单

- 对每个 MP4 运行 `ffprobe`，确认分辨率、时长、帧率、音频编码、采样率与声道数。
- 抽查开头、中段、结尾的截图。
- 确认竖版字幕未与底部安全区、右侧平台控件重叠。
- 确认标题与元信息未溢出。
- 在生成的 ASS 中检索已知垃圾片段（如 `优优`、`YoYo`、`Exclusive` 等）。
- 完整版渲染后，将时长与原始音频对比。

## 常见问题排查

- **Windows 路径下 ASS 字幕失败**：使用绝对路径，并保留脚本内的 FFmpeg 路径转义逻辑。
- **中文显示为方块**：安装微软雅黑、Noto Sans CJK 或 PingFang 后重跑。
- **字幕时间轴漂移**：从原始音频重新生成转写，避免使用 VBR 派生的中间文件。
- **输出文件过大**：将脚本中的 CRF 调到 22–24，或增加码率上限。
- **波形太平**：保持 `scale=sqrt`，对话类音频不要用线性缩放。

## 使用建议

- 最终成片请使用原始音频，不要用低码率 ASR 音频合成。
- 短视频平台建议烧录字幕，除非用户明确需要外挂字幕文件。
- 竖版字幕应放在底部 UI 区上方，并远离右侧平台控件。
- ASR 字幕用于审阅通常够用，点正式上传前建议人工快速校对人名、术语、日期与片尾内容。
- 请勿把生成的 MP4、whisper 模型或本地下载的单集文件提交进技能仓库。
