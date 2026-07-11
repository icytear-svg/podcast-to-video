---
name: podcast-to-video
description: Convert podcast episodes or audio programs into platform-ready horizontal and vertical videos with looping video backgrounds or classic cover-art backgrounds, episode artwork/logo, title, guest/host metadata, keywords, and accurate synced Chinese subtitles. Use when Codex is asked to make podcast videos for Douyin, WeChat Channels, Bilibili, Xiaohongshu, YouTube Shorts/Reels-style platforms, reproduce the approved style1 layout, or batch-generate captioned video assets from RSS/Xiaoyuzhou metadata, audio, cover art, SRT/ASR transcripts, and reusable background clips.
---

# Podcast To Video

## Core Workflow

1. Gather inputs: original high-quality audio, square episode cover, episode title/number, podcast name, guest, host, keywords, transcript, target platforms, and optional looping background clips.
2. Prefer an existing official transcript or exported SRT. If no transcript exists, generate one with a reliable ASR path, then apply a small glossary with `--correction`.
3. Select the visual style:
   - Use `scripts/loop_background_video.py` when background clips are provided or the user requests style1. This style has no waveform or progress bar and uses one-line subtitles.
   - Use `scripts/podcast_video.py` for the classic blurred-cover style with waveform, progress bar, and production metadata.
4. Build both layouts unless the user asks otherwise:
   - `vertical` 1080x1920 for Douyin, WeChat Channels, Xiaohongshu, Shorts/Reels.
   - `horizontal` 1920x1080 for Bilibili and long-form video platforms.
5. Render a short sample first when developing a new show or background style. After approval, render the full episode with the same style config.
6. Inspect generated screenshots, ASS text, and `ffprobe` output before delivery. Production subtitles still need a quick human pass for names, terms, dates, and episode endings.

## Loop Background Style

Use style1 for the approved warm, editorial layout with a looping video background, prominent episode cover, guest/host chips, keyword chips, and a large single-line subtitle panel:

```powershell
python "<skill-dir>\scripts\loop_background_video.py" `
  --audio "<episode>.m4a" `
  --cover "<cover>.png" `
  --srt "<transcript>.srt" `
  --horizontal-bg-video "<horizontal-loop>.mp4" `
  --vertical-bg-video "<vertical-loop>.mp4" `
  --podcast-name "苦中找乐" `
  --episode-no "093" `
  --title "上职高的孩子什么样？在职高当老师有啥体验？" `
  --guest "小马" `
  --host "羊行" `
  --keyword "职业教育" --keyword "职高老师" `
  --correction "杨航=羊行" `
  --mode sample --duration 30 `
  --stem "093_style1"
```

Use `--metadata-json` instead of repeated metadata arguments for batch work. CLI values override JSON values. Read `references/loop-background-style.md` before changing style1 geometry, subtitle behavior, background handling, or QA rules.

## Classic Style

Use the bundled script from the skill directory:

```powershell
python "<skill-dir>\scripts\podcast_video.py" `
  --audio "<episode>.m4a" `
  --cover "<cover>.png" `
  --srt "<transcript>.srt" `
  --podcast-name "苦中找乐" `
  --title "上职高的孩子什么样？在职高当老师有啥体验？" `
  --episode-tag "对谈 夜夜页页小马 - 093" `
  --guest "小马（夜夜页页主播）" `
  --host "羊行" `
  --recorded-at "2026年5月11日" `
  --published-at "2026年6月29日" `
  --mode full `
  --stem "093_full" `
  --work-dir ".\video_work" `
  --output-dir ".\video_outputs" `
  --correction "杨航=羊行"
```

If there is no SRT but FFmpeg has the `whisper` filter and a whisper.cpp model is available:

```powershell
python "<skill-dir>\scripts\podcast_video.py" `
  --audio "<episode>.m4a" `
  --cover "<cover>.png" `
  --asr-model "<models>\ggml-large-v3-turbo-q5_0.bin" `
  --podcast-name "节目名" `
  --title "当期标题" `
  --mode full
```

Both scripts produce MP4s, ASS subtitle files, static overlays/backgrounds, key screenshots, and a JSON manifest.

## Rules

- Use the original audio for the final video. Do not synthesize the final from low-bitrate ASR audio.
- Keep subtitles burned in for short-video platforms unless the user explicitly needs sidecar caption files.
- Keep vertical subtitles above the bottom UI area and away from right-side platform controls.
- Check the last minute of subtitles for ASR hallucinations caused by music, silence, or credits. Use `--banned-fragment` for show-specific junk strings.
- Use glossary corrections for host names, guest names, podcast names, and recurring terms.
- Keep style1 subtitles to one line. Split long cues sequentially by rendered pixel width; never insert `\N` to force two lines.
- Keep background clips external to the skill. Pass them per job so new visual themes can reuse the same renderer.
- Do not commit generated MP4s, whisper models, or local episode downloads into the skill repository.

## References

Read `references/pipeline.md` when setting up a new show, adapting metadata formats, choosing ASR strategy, or debugging general subtitle/video QA.

Read `references/loop-background-style.md` when using style1, adding a reusable looping-background style, or tuning horizontal/vertical layouts.
