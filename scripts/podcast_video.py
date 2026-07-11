# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


SCRIPT_DIR = Path(__file__).resolve().parent

FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/msyh.ttc"),
    Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"),
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
]
BOLD_FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/msyhbd.ttc"),
    Path("C:/Windows/Fonts/NotoSansSC-VF.ttf"),
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
]

ACCENT = (249, 194, 107)
ACCENT_DARK = (40, 104, 86)
INK = (245, 246, 238)
MUTED = (202, 208, 196)
PANEL_DARK = (10, 15, 14)
BADGE_FILL = (31, 43, 37)
BADGE_OUTLINE = (91, 106, 91)
RULE = (164, 137, 83)

DEFAULT_BANNED_FRAGMENTS = [
    "优优独播剧场",
    "YoYo Television Series",
]


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class Episode:
    podcast_name: str
    title: str
    episode_tag: str
    guest: str
    host: str
    recorded_at: str
    published_at: str
    segment_label: str


@dataclass
class BuildConfig:
    mode: str
    stem: str
    start: float
    duration: float
    audio: Path
    cover: Path
    srt: Path
    work_dir: Path
    output_dir: Path
    layouts: list[str]
    episode: Episode
    corrections: dict[str, str]
    banned_fragments: list[str]
    screenshots: bool


@dataclass
class Layout:
    name: str
    size: tuple[int, int]
    cover_box: tuple[int, int, int, int]
    title_xy: tuple[int, int]
    title_width: int
    meta_xy: tuple[int, int]
    wave_box: tuple[int, int, int, int]
    subtitle_font: int
    subtitle_margin_v: int
    subtitle_line_chars: int
    subtitle_max_chars: int
    subtitle_outline: int


LAYOUTS = {
    "vertical": Layout(
        name="vertical",
        size=(1080, 1920),
        cover_box=(260, 182, 560, 560),
        title_xy=(100, 770),
        title_width=880,
        meta_xy=(100, 1038),
        wave_box=(110, 1316, 860, 130),
        subtitle_font=60,
        subtitle_margin_v=245,
        subtitle_line_chars=14,
        subtitle_max_chars=27,
        subtitle_outline=3,
    ),
    "horizontal": Layout(
        name="horizontal",
        size=(1920, 1080),
        cover_box=(126, 156, 560, 560),
        title_xy=(780, 164),
        title_width=930,
        meta_xy=(780, 478),
        wave_box=(780, 706, 980, 110),
        subtitle_font=54,
        subtitle_margin_v=76,
        subtitle_line_chars=24,
        subtitle_max_chars=46,
        subtitle_outline=3,
    ),
}


def resolve(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def first_existing(paths: Iterable[Path]) -> Path | None:
    return next((path for path in paths if path.exists()), None)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = first_existing(BOLD_FONT_CANDIDATES if bold else FONT_CANDIDATES)
    if path:
        return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def parse_kv(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=>" in item:
            left, right = item.split("=>", 1)
        elif "=" in item:
            left, right = item.split("=", 1)
        else:
            raise ValueError(f"Expected KEY=VALUE correction, got: {item}")
        out[left] = right
    return out


def parse_corrections(value: object) -> dict[str, str]:
    """Accept both documented KEY=VALUE lists and JSON object mappings."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(key): str(replacement) for key, replacement in value.items()}
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return parse_kv(value)
    raise ValueError("corrections must be an object or a list of KEY=VALUE strings")


def bounded_segment(audio_length: float, mode: str, start: float | None, duration: float | None) -> tuple[float, float]:
    segment_start = max(0.0, start or 0.0)
    remaining = audio_length - segment_start
    if remaining <= 0:
        raise ValueError("start/duration is outside the audio")
    requested = duration if duration is not None else (remaining if mode == "full" else 75.0)
    segment_duration = min(requested, remaining)
    if segment_duration <= 0:
        raise ValueError("duration must be greater than zero")
    return segment_start, segment_duration


def audio_duration(audio: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(audio),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return float(result.stdout.strip())


def duration_label(seconds: float) -> str:
    total = int(round(seconds))
    minutes, sec = divmod(total, 60)
    return f"{minutes:02d}:{sec:02d}"


def load_metadata(path: Path | None) -> dict:
    if not path:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def meta_value(args: argparse.Namespace, metadata: dict, key: str, default: str = "") -> str:
    cli_name = key.replace("-", "_")
    value = getattr(args, cli_name, None)
    if value not in (None, ""):
        return value
    return str(metadata.get(cli_name, metadata.get(key, default)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build vertical and horizontal podcast videos with ASS subtitles.")
    parser.add_argument("--audio", required=True, help="Original high-quality audio file.")
    parser.add_argument("--cover", required=True, help="Episode art or podcast logo image.")
    parser.add_argument("--srt", help="Subtitle SRT file. Required unless --asr-model is provided.")
    parser.add_argument("--asr-model", help="Optional whisper.cpp ggml model; generates SRT through FFmpeg whisper filter.")
    parser.add_argument("--language", default="zh", help="ASR language for FFmpeg whisper filter.")
    parser.add_argument("--metadata-json", type=Path, help="Optional JSON metadata file.")
    parser.add_argument("--podcast-name", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--episode-tag", default="")
    parser.add_argument("--guest", default="")
    parser.add_argument("--host", default="")
    parser.add_argument("--recorded-at", default="")
    parser.add_argument("--published-at", default="")
    parser.add_argument("--segment-label", default="")
    parser.add_argument("--mode", choices=["sample", "full"], default="sample")
    parser.add_argument("--start", type=float, default=None, help="Audio start offset in seconds.")
    parser.add_argument("--duration", type=float, default=None, help="Output duration in seconds.")
    parser.add_argument("--stem", default="", help="Output filename stem.")
    parser.add_argument("--work-dir", default="podcast_video_work")
    parser.add_argument("--output-dir", default="podcast_video_outputs")
    parser.add_argument("--layout", action="append", choices=["vertical", "horizontal"], default=[])
    parser.add_argument("--correction", action="append", default=[], help="Subtitle correction, e.g. '杨航=羊行'.")
    parser.add_argument("--banned-fragment", action="append", default=[], help="Drop subtitle cues containing this text.")
    parser.add_argument("--no-screenshots", action="store_true")
    return parser.parse_args()


def make_config(args: argparse.Namespace) -> BuildConfig:
    metadata = load_metadata(args.metadata_json)
    audio = resolve(args.audio)
    cover = resolve(args.cover)
    work_dir = resolve(args.work_dir)
    output_dir = resolve(args.output_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = args.stem or re.sub(r"[^0-9A-Za-z_-]+", "_", audio.stem).strip("_") or "podcast_video"
    start, duration = bounded_segment(audio_duration(audio), args.mode, args.start, args.duration)
    segment_label = meta_value(args, metadata, "segment-label")
    if not segment_label:
        segment_label = f"完整版 {duration_label(duration)}" if args.mode == "full" else f"样片 {duration_label(duration)}"

    srt = resolve(args.srt) if args.srt else work_dir / f"{stem}_whisper.srt"
    episode = Episode(
        podcast_name=meta_value(args, metadata, "podcast-name", "Podcast"),
        title=meta_value(args, metadata, "title", audio.stem),
        episode_tag=meta_value(args, metadata, "episode-tag", ""),
        guest=meta_value(args, metadata, "guest", ""),
        host=meta_value(args, metadata, "host", ""),
        recorded_at=meta_value(args, metadata, "recorded-at", ""),
        published_at=meta_value(args, metadata, "published-at", ""),
        segment_label=segment_label,
    )
    corrections = parse_corrections(metadata.get("corrections"))
    corrections.update(parse_kv(args.correction))
    banned = DEFAULT_BANNED_FRAGMENTS + list(metadata.get("banned_fragments", [])) + args.banned_fragment
    layouts = args.layout or ["vertical", "horizontal"]

    config = BuildConfig(
        mode=args.mode,
        stem=stem,
        start=start,
        duration=duration,
        audio=audio,
        cover=cover,
        srt=srt,
        work_dir=work_dir,
        output_dir=output_dir,
        layouts=layouts,
        episode=episode,
        corrections=corrections,
        banned_fragments=banned,
        screenshots=not args.no_screenshots,
    )
    if not srt.exists():
        if not args.asr_model:
            raise FileNotFoundError(f"SRT not found and --asr-model was not provided: {srt}")
        run_asr(config, resolve(args.asr_model), args.language)
    return config


def filter_path(path: Path) -> str:
    return path.as_posix().replace(":", r"\:")


def run_asr(config: BuildConfig, model: Path, language: str) -> None:
    destination = filter_path(config.srt)
    model_path = filter_path(model)
    audio_filter = (
        f"whisper=model={model_path}:language={language}:queue=30:"
        f"destination={destination}:format=srt:max_len=32"
    )
    null_target = "NUL" if os.name == "nt" else "/dev/null"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-i", str(config.audio), "-vn", "-af", audio_filter, "-f", "null", null_target],
        check=True,
    )


def draw_round_rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text_width(draw: ImageDraw.ImageDraw, text: str, fnt) -> int:
    return math.ceil(draw.textbbox((0, 0), text, font=fnt)[2])


def wrap_by_width(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> list[str]:
    rows: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and text_width(draw, candidate, fnt) > max_width:
            rows.append(current)
            current = char
        else:
            current = candidate
    if current:
        rows.append(current)
    return rows


def draw_multiline(draw: ImageDraw.ImageDraw, xy: tuple[int, int], lines: Iterable[str], fnt, fill, spacing: int = 12) -> int:
    x, y = xy
    for line in lines:
        box = draw.textbbox((x, y), line, font=fnt)
        draw.text((x, y), line, font=fnt, fill=fill)
        y += box[3] - box[1] + spacing
    return y


def draw_right_text(draw: ImageDraw.ImageDraw, right: int, y: int, text: str, fnt, fill) -> None:
    draw.text((right - text_width(draw, text, fnt), y), text, font=fnt, fill=fill)


def paste_cover(base: Image.Image, cover: Image.Image, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x + 18, y + 24, x + w + 18, y + h + 24), radius=36, fill=(0, 0, 0, 100))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    base.alpha_composite(shadow)

    fitted = ImageOps.fit(cover.convert("RGB"), (w, h), method=Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=30, fill=255)
    border = Image.new("RGBA", (w + 8, h + 8), (0, 0, 0, 0))
    bd = ImageDraw.Draw(border)
    bd.rounded_rectangle((0, 0, w + 7, h + 7), radius=34, fill=(255, 255, 255, 28), outline=(255, 255, 255, 70), width=3)
    base.alpha_composite(border, (x - 4, y - 4))
    base.paste(fitted, (x, y), mask)


def draw_badge(draw: ImageDraw.ImageDraw, xy: tuple[int, int], label: str, value: str, max_width: int) -> int:
    if not value:
        value = "-"
    label_font = font(30)
    value_size = 32
    value_font = font(value_size)
    x, y = xy
    label_w = text_width(draw, label, label_font)
    available = max(120, max_width - label_w - 70)
    while value_size > 23 and text_width(draw, value, value_font) > available:
        value_size -= 1
        value_font = font(value_size)
    value_w = min(text_width(draw, value, value_font), available)
    box_w = min(max_width, label_w + value_w + 82)
    box_h = 62
    draw_round_rect(draw, (x, y, x + box_w, y + box_h), 18, BADGE_FILL, BADGE_OUTLINE, 1)
    draw.text((x + 22, y + 14), label, font=label_font, fill=ACCENT)
    draw.text((x + 22 + label_w + 22, y + 12), value, font=value_font, fill=INK)
    return box_w


def make_background(layout: Layout, config: BuildConfig) -> Path:
    cover = Image.open(config.cover)
    w, h = layout.size
    bg = ImageOps.fit(cover.convert("RGB"), (w, h), method=Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(34)).convert("RGBA")
    bg.alpha_composite(Image.new("RGBA", (w, h), (9, 13, 12, 178)))
    draw = ImageDraw.Draw(bg)

    if layout.name == "vertical":
        draw.rectangle((0, 0, w, 92), fill=ACCENT_DARK)
        draw.rectangle((0, h - 20, w, h), fill=ACCENT + (230,))
        draw.line((80, 724, 1000, 724), fill=RULE, width=2)
        draw_round_rect(draw, (82, 1268, 998, 1522), 28, PANEL_DARK, BADGE_OUTLINE, 1)
        draw.text((92, 31), config.episode.podcast_name, font=font(36), fill=INK)
        draw_right_text(draw, w - 92, 33, config.episode.episode_tag, font(28), (235, 238, 225))
    else:
        draw.rectangle((0, 0, w, 76), fill=ACCENT_DARK)
        draw.rectangle((0, h - 14, w, h), fill=ACCENT + (230,))
        draw_round_rect(draw, (738, 662, 1802, 846), 28, PANEL_DARK, BADGE_OUTLINE, 1)
        draw.text((88, 24), config.episode.podcast_name, font=font(30), fill=INK)
        draw_right_text(draw, w - 88, 24, config.episode.episode_tag, font(26), (235, 238, 225))

    paste_cover(bg, cover, layout.cover_box)

    title_font = font(62 if layout.name == "vertical" else 66, bold=True)
    tag_font = font(32)
    title_lines = wrap_by_width(draw, config.episode.title, title_font, layout.title_width)
    y = draw_multiline(draw, layout.title_xy, title_lines, title_font, INK, spacing=8)
    if config.episode.episode_tag:
        draw.text((layout.title_xy[0], y + 8), config.episode.episode_tag, font=tag_font, fill=ACCENT)

    rows = [
        ("嘉宾", config.episode.guest),
        ("主播", config.episode.host),
        ("录制", config.episode.recorded_at),
        ("发布", config.episode.published_at),
        ("片段", config.episode.segment_label),
    ]
    mx, my = layout.meta_xy
    if layout.name == "vertical":
        pairs = [(rows[0], rows[1]), (rows[2], rows[3])]
        row_y = my
        for left, right in pairs:
            draw_badge(draw, (mx, row_y), left[0], left[1], 425)
            draw_badge(draw, (mx + 455, row_y), right[0], right[1], 425)
            row_y += 74
        draw_badge(draw, (mx, row_y), rows[4][0], rows[4][1], 560)
    else:
        row_y = my
        for idx, (label, value) in enumerate(rows):
            if idx % 2 == 1:
                continue
            draw_badge(draw, (mx, row_y), label, value, 470)
            if idx + 1 < len(rows):
                draw_badge(draw, (mx + 510, row_y), rows[idx + 1][0], rows[idx + 1][1], 470)
            row_y += 76

    wx, wy, ww, wh = layout.wave_box
    draw.text((wx + 28, wy + 22), "声音波形", font=font(28), fill=MUTED)
    draw.text((wx + ww - 190, wy + 22), "中文字幕已对齐", font=font(28), fill=ACCENT)
    draw.line((wx + 28, wy + wh - 34, wx + ww - 28, wy + wh - 34), fill=BADGE_OUTLINE, width=1)

    out = config.work_dir / f"{config.stem}_{layout.name}_bg.png"
    bg.convert("RGB").save(out, quality=95)
    return out


def parse_srt_time(value: str) -> float:
    hh, mm, rest = value.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000


def format_ass_time(seconds: float) -> str:
    seconds = max(0, seconds)
    cs = int(round(seconds * 100))
    hh, rem = divmod(cs, 360000)
    mm, rem = divmod(rem, 6000)
    ss, cc = divmod(rem, 100)
    return f"{hh}:{mm:02d}:{ss:02d}.{cc:02d}"


def parse_srt(path: Path) -> list[Cue]:
    raw = path.read_text(encoding="utf-8-sig").strip()
    blocks = re.split(r"\n\s*\n", raw)
    cues: list[Cue] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_line = next((line for line in lines if "-->" in line), "")
        if not time_line:
            continue
        start_s, end_s = [part.strip() for part in time_line.split("-->")]
        text = " ".join(lines[lines.index(time_line) + 1 :]).strip()
        cues.append(Cue(parse_srt_time(start_s), parse_srt_time(end_s), text))
    return cues


def clean_text(text: str, config: BuildConfig) -> str:
    text = text.strip()
    if any(fragment.lower() in text.lower() for fragment in config.banned_fragments):
        return ""
    for wrong, right in config.corrections.items():
        text = text.replace(wrong, right)
    text = re.sub(r"\s+", "", text)
    return text


def make_readable_cues(cues: list[Cue], layout: Layout, config: BuildConfig) -> list[Cue]:
    cleaned = []
    for cue in cues:
        text = clean_text(cue.text, config)
        if not text:
            continue
        if cue.end - cue.start > 6 and text in {"拜拜", "OK"}:
            continue
        if cue.end <= config.start or cue.start >= config.start + config.duration:
            continue
        cleaned.append(Cue(max(0, cue.start - config.start), min(config.duration, cue.end - config.start), text))

    cleaned.sort(key=lambda c: (c.start, c.end))
    for i in range(1, len(cleaned)):
        if cleaned[i].start < cleaned[i - 1].end:
            cleaned[i].start = min(cleaned[i].end - 0.08, cleaned[i - 1].end + 0.02)

    grouped: list[Cue] = []
    current: list[Cue] = []

    def flush() -> None:
        if current:
            grouped.append(Cue(current[0].start, current[-1].end, "".join(c.text for c in current)))
            current.clear()

    for cue in cleaned:
        if not current:
            current.append(cue)
            continue
        duration = cue.end - current[0].start
        chars = sum(len(c.text) for c in current) + len(cue.text)
        gap = cue.start - current[-1].end
        if gap > 0.38 or duration > 4.2 or chars > layout.subtitle_max_chars:
            flush()
        current.append(cue)
        if cue.end - current[0].start >= 1.35 and sum(len(c.text) for c in current) >= layout.subtitle_max_chars * 0.72:
            flush()
    flush()

    for i in range(len(grouped) - 1):
        if grouped[i].end > grouped[i + 1].start:
            grouped[i].end = max(grouped[i].start + 0.42, grouped[i + 1].start - 0.02)
    return grouped


def split_caption(text: str, chars_per_line: int) -> str:
    if len(text) <= chars_per_line:
        return text
    if len(text) <= chars_per_line * 2:
        split_at = math.ceil(len(text) / 2)
        for distance in range(0, 6):
            for pos in (split_at - distance, split_at + distance):
                if 1 < pos < len(text) - 1 and text[pos - 1] in "，。、！？；：":
                    split_at = pos
                    return text[:split_at] + r"\N" + text[split_at:]
        return text[:split_at] + r"\N" + text[split_at:]
    lines: list[str] = []
    current = ""
    for char in text:
        current += char
        if len(current) >= chars_per_line:
            split_at = len(current)
            for idx in range(len(current) - 1, max(0, len(current) - 7), -1):
                if current[idx] in "，。、！？；：":
                    split_at = idx + 1
                    break
            lines.append(current[:split_at])
            current = current[split_at:]
    if current:
        lines.append(current)
    return r"\N".join(lines[:2])


def ass_escape(text: str) -> str:
    return text.replace("{", r"\{").replace("}", r"\}")


def write_ass(layout: Layout, cues: list[Cue], config: BuildConfig) -> Path:
    w, h = layout.size
    ass_path = config.work_dir / f"{config.stem}_{layout.name}.ass"
    events = []
    for cue in make_readable_cues(cues, layout, config):
        text = ass_escape(split_caption(cue.text, layout.subtitle_line_chars))
        events.append(f"Dialogue: 0,{format_ass_time(cue.start)},{format_ass_time(cue.end)},Caption,,0,0,0,,{text}")
    ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Microsoft YaHei,{layout.subtitle_font},&H00F7F8F1,&H000000FF,&HCC0B0F0E,&H99000000,-1,0,0,0,100,100,0,0,1,{layout.subtitle_outline},1.4,2,70,70,{layout.subtitle_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""
    ass_path.write_text(ass, encoding="utf-8")
    return ass_path


def run_ffmpeg(layout: Layout, bg_path: Path, ass_path: Path, config: BuildConfig) -> Path:
    out_path = config.output_dir / f"{config.stem}_{layout.name}_{layout.size[0]}x{layout.size[1]}.mp4"
    wx, wy, ww, wh = layout.wave_box
    filter_complex = (
        f"[1:a]showwaves=s={ww}x{wh - 70}:mode=line:scale=sqrt:rate=30:colors=0xF9C26B,format=rgba[wave];"
        f"[0:v][wave]overlay={wx}:{wy + 66}[v1];"
        f"[v1]ass='{filter_path(ass_path)}',"
        f"drawbox=x=0:y=ih-12:w=iw*t/{config.duration}:h=12:color=0xF9C26B@0.95:t=fill[v]"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        str(config.duration),
        "-i",
        str(bg_path),
        "-ss",
        str(config.start),
        "-t",
        str(config.duration),
        "-i",
        str(config.audio),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "1:a",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path


def make_screenshot(video_path: Path, at_seconds: int, work_dir: Path) -> Path:
    shot = work_dir / f"{video_path.stem}_t{at_seconds:04d}.png"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-ss", str(at_seconds), "-i", str(video_path), "-frames:v", "1", "-update", "1", str(shot)],
        check=True,
    )
    if not shot.is_file() or shot.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg did not create screenshot at {at_seconds}s: {shot}")
    return shot


def screenshot_times(config: BuildConfig) -> list[int]:
    duration = max(1, int(config.duration))
    if duration <= 90:
        candidates = [6, duration // 2, max(1, duration - 15)]
    else:
        candidates = [30, duration // 2, max(1, duration - 45)]
    return sorted({min(max(1, sec), duration - 1) for sec in candidates})


def ffprobe(video_path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(video_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def main() -> None:
    config = make_config(parse_args())
    missing = [str(path) for path in (config.audio, config.cover, config.srt) if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required files: " + ", ".join(missing))

    cues = parse_srt(config.srt)
    outputs = {}
    for layout_name in config.layouts:
        layout = LAYOUTS[layout_name]
        bg = make_background(layout, config)
        ass = write_ass(layout, cues, config)
        video = run_ffmpeg(layout, bg, ass, config)
        shots = [make_screenshot(video, sec, config.work_dir) for sec in screenshot_times(config)] if config.screenshots else []
        outputs[layout.name] = {
            "background": str(bg),
            "subtitles": str(ass),
            "video": str(video),
            "screenshots": [str(path) for path in shots],
            "probe": ffprobe(video),
        }

    manifest = config.output_dir / f"{config.stem}_manifest.json"
    manifest.write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({name: data["video"] for name, data in outputs.items()}, ensure_ascii=False, indent=2))
    print(f"Manifest: {manifest}")


if __name__ == "__main__":
    main()
