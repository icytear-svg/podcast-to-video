# Podcast Video Pipeline Reference

## Inputs

Minimum inputs:

- Original audio: `.m4a`, `.mp3`, or `.wav`.
- Cover/logo image: preferably square, at least 1000px wide.
- Metadata: podcast name, episode title, guest, host, recording date, publish date, episode tag.
- Transcript: SRT preferred. If missing, generate with ASR.
- Optional looping background videos: 16:9 for horizontal and 9:16 for vertical.

Optional metadata JSON:

```json
{
  "podcast_name": "苦中找乐",
  "episode_no": "093",
  "title": "上职高的孩子什么样？在职高当老师有啥体验？",
  "title_lines": ["上职高的孩子什么样？", "在职高当老师有啥体验？"],
  "episode_tag": "对谈 夜夜页页小马 - 093",
  "guest": "小马（夜夜页页主播）",
  "host": "羊行",
  "recorded_at": "2026年5月11日",
  "published_at": "2026年6月29日",
  "keywords": ["职业教育", "职高老师", "青少年"],
  "horizontal_bg_video": "C:/media/loop-horizontal.mp4",
  "vertical_bg_video": "C:/media/loop-vertical.mp4",
  "corrections": ["杨航=羊行", "博客=播客"],
  "banned_fragments": ["YoYo Television Series"]
}
```

CLI values override JSON values.

## Visual Style Selection

- Use `loop_background_video.py` for style1 or supplied loop clips. It renders at 24 fps with large one-line subtitles and no waveform/progress bar. See `loop-background-style.md`.
- Use `podcast_video.py` for the classic blurred-cover treatment with waveform, progress bar, dates, and segment metadata.

## ASR Strategy

Use this priority order:

1. Official or producer-provided SRT/ASS/VTT with timestamps.
2. Platform transcript export from a logged-in source.
3. Cloud ASR with glossary support.
4. Local FFmpeg `whisper` filter with a whisper.cpp model.

For Chinese podcast samples, `large-v3-turbo` quality is usually much better than small models. Use a correction glossary for names, show titles, and recurring domain terms. Inspect the last minute for hallucinations after music/silence.

## Platform Presets

The script currently renders:

- `vertical`: 1080x1920, 30fps, burned subtitles, suitable for Douyin, WeChat Channels, Xiaohongshu, Shorts/Reels.
- `horizontal`: 1920x1080, 30fps, burned subtitles, suitable for Bilibili and long-form platforms.

Both layouts include:

- Blurred/dimmed cover art background.
- Sharp cover/logo.
- Podcast name, episode title, guest, host, recording date, publish date, segment label.
- Animated waveform.
- Bottom progress bar.
- ASS-rendered subtitles.

## QA Checklist

Before delivery:

- Run `ffprobe` on every MP4 and confirm width, height, duration, frame rate, audio codec, sample rate, and channels.
- Inspect screenshots near the beginning, middle, and end.
- Confirm vertical subtitles do not collide with bottom safe area.
- Confirm title and metadata do not overflow.
- Search rendered ASS for known bad fragments:

```powershell
rg -n "YoYo|优优|Exclusive|<wrong-name>" "<work-dir>\*.ass"
```

- For style1, also confirm ASS contains no `\\N` and every subtitle fits as one line.

- Compare duration to the original audio when rendering full episodes.
- If uploading to platforms, spot-check the first 60 seconds, a middle section, and the ending after upload processing.

## Common Commands

For loop-background style commands and metadata, see `loop-background-style.md`.

Generate a 75-second sample from `02:25`:

```powershell
python "<skill-dir>\scripts\podcast_video.py" `
  --audio ".\episode.m4a" `
  --cover ".\cover.png" `
  --srt ".\episode.srt" `
  --podcast-name "节目名" `
  --title "标题" `
  --start 145 `
  --duration 75 `
  --mode sample `
  --stem "episode_sample"
```

Generate a full episode with both layouts:

```powershell
python "<skill-dir>\scripts\podcast_video.py" `
  --audio ".\episode.m4a" `
  --cover ".\cover.png" `
  --srt ".\episode.srt" `
  --metadata-json ".\metadata.json" `
  --mode full `
  --stem "episode_full"
```

Render only vertical:

```powershell
python "<skill-dir>\scripts\podcast_video.py" `
  --audio ".\episode.m4a" `
  --cover ".\cover.png" `
  --srt ".\episode.srt" `
  --podcast-name "节目名" `
  --title "标题" `
  --layout vertical
```

## Troubleshooting

- If ASS subtitles fail on Windows paths, use absolute paths and keep FFmpeg path escaping in the script.
- If Chinese characters render as boxes, install Microsoft YaHei, Noto Sans CJK, or PingFang and rerun.
- If SRT timing drifts, regenerate transcript from the original audio and avoid VBR-derived intermediate files.
- If output files are too large, increase CRF to 22-24 in the script or add a bitrate cap.
- If waveform looks too flat, keep `scale=sqrt`; avoid linear scale for conversational audio.
