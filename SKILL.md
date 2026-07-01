---
name: podcast-to-video
description: Convert podcast episodes or audio programs into platform-ready videos with episode artwork/logo, title, guest/host metadata, recording/publish dates, waveform, progress bar, and accurate synced Chinese subtitles. Use when Codex is asked to make horizontal or vertical podcast videos for Douyin, WeChat Channels, Bilibili, Xiaohongshu, YouTube Shorts/Reels-style platforms, or to batch-generate captioned podcast video assets from audio, cover art, SRT/ASR transcripts, RSS/Xiaoyuzhou metadata, or local episode files.
---

# Podcast To Video

## Core Workflow

1. Gather inputs: original high-quality audio, square cover/logo image, episode title, podcast name, guest, host, recording date, publish date, and target platforms.
2. Prefer an existing official transcript or exported SRT. If no transcript exists, generate one with a reliable ASR path, then apply a small glossary with `--correction`.
3. Build both layouts unless the user asks otherwise:
   - `vertical` 1080x1920 for Douyin, WeChat Channels, Xiaohongshu, Shorts/Reels.
   - `horizontal` 1920x1080 for Bilibili and long-form video platforms.
4. Render with `scripts/podcast_video.py`, then inspect screenshots and `ffprobe` output before handing over final videos.
5. Report subtitle limitations clearly. ASR subtitles can be good enough for review, but production uploads should still get a quick human pass for names, terms, dates, and episode endings.

## Script

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

Outputs include vertical/horizontal MP4s, ASS subtitle files, background images, key screenshots, and a JSON manifest.

## Rules

- Use the original audio for the final video. Do not synthesize the final from low-bitrate ASR audio.
- Keep subtitles burned in for short-video platforms unless the user explicitly needs sidecar caption files.
- Keep vertical subtitles above the bottom UI area and away from right-side platform controls.
- Check the last minute of subtitles for ASR hallucinations caused by music, silence, or credits. Use `--banned-fragment` for show-specific junk strings.
- Use glossary corrections for host names, guest names, podcast names, and recurring terms.
- Do not commit generated MP4s, whisper models, or local episode downloads into the skill repository.

## References

Read `references/pipeline.md` when setting up a new show, adapting metadata formats, choosing ASR strategy, or debugging subtitle/video QA.
