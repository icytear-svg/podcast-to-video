# Loop Background Style

## When To Use

Use `scripts/loop_background_video.py` when a show supplies reusable looping background clips or requests style1. Keep `scripts/podcast_video.py` for the classic blurred-cover, waveform, and progress-bar treatment.

Style1 separates the moving background from a static foreground overlay. Per-episode data changes the cover, title, people, keywords, subtitles, and episode number; the approved geometry remains in `assets/styles/style1-*.json`.

## Required Inputs

- Original audio and square episode cover.
- SRT synchronized to the original audio.
- Podcast name, episode number, title, guest, host, and 3-5 short keywords.
- A 16:9 loop clip for horizontal output and/or a 9:16 loop clip for vertical output.

Optional metadata JSON:

```json
{
  "podcast_name": "苦中找乐",
  "episode_no": "093",
  "title": "上职高的孩子什么样？在职高当老师有啥体验？",
  "title_lines": ["上职高的孩子什么样？", "在职高当老师有啥体验？"],
  "guest": "小马",
  "host": "羊行",
  "keywords": ["职业教育", "职高老师", "青少年", "成长困境"],
  "horizontal_bg_video": "C:/media/loop-horizontal.mp4",
  "vertical_bg_video": "C:/media/loop-vertical.mp4",
  "corrections": {"杨航": "羊行"},
  "banned_fragments": ["YoYo", "Exclusive"]
}
```

CLI values override metadata JSON. Use repeated `--keyword`, `--title-line`, `--correction`, and `--banned-fragment` arguments where appropriate.

## Approved Style1 Rules

Horizontal is 1920x1080 at 24 fps. Keep the show identity and title on the left, the 542px episode cover on the upper right, people and keywords below the title, and the subtitle panel across the lower third.

Vertical is 1080x1920 at 24 fps. Use the translucent main card, centered 560px episode cover, title and chips inside the card, and the detached subtitle panel below it.

For both layouts:

- Loop and cover-fit the supplied background clip; never stretch it.
- Show the episode cover prominently.
- Put guest and host in labeled chips; do not add an extra “当期关键词” label.
- Do not show a waveform, progress bar, “背景” label, or slash-separated duplicate metadata line.
- Keep the foreground card/boxes opaque enough to separate information from the moving background.
- Keep subtitles centered, large, and one line only with no outline or shadow.

## Subtitle Policy

Apply glossary corrections before layout. Remove known ASR junk with banned fragments. The renderer measures text with the production font and splits an over-wide cue into consecutive one-line cues, distributing the original cue duration by text length. It never uses an ASS line break.

Inspect the final minute. Music and silence can produce repeated names, English network phrases, or long “拜拜/谢谢” cues. The renderer removes common junk and trims implausibly long farewell cues; use `--keep-post-farewell-subtitles` only when verified credits must remain.

## Extending Styles

Copy both JSON style configs to a job-owned style directory, change geometry/colors there, and pass it with `--style-dir`. Keep media, generated overlays, ASS files, screenshots, and MP4s outside the skill repository. A new style should preserve the same metadata and subtitle contract so batch jobs do not need renderer changes.

## QA

Before full rendering, produce a 10-30 second sample for each requested orientation. For final delivery:

- Confirm resolution, 24 fps, duration, H.264 video, and AAC audio with `ffprobe`.
- Inspect beginning, middle, and ending screenshots for cover crop, title overflow, chip wrapping, subtitle fit, and background contrast.
- Search ASS files for wrong names, banned fragments, and `\\N`.
- Compare full-video duration with the source audio.
- Spot-check the first minute, a middle passage, and the ending with sound.
