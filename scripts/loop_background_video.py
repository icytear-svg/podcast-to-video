from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STYLE_DIR = SKILL_DIR / "assets" / "styles"
DEFAULT_BANNED = ["YoYo", "优优", "Exclusive", "Television Series", "独播剧场"]
FONT_CANDIDATES = {
    "regular": [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ],
    "bold": [
        Path(r"C:\Windows\Fonts\msyhbd.ttc"),
        Path(r"C:\Windows\Fonts\msyhbd.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ],
}


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class Context:
    audio: Path
    cover: Path
    srt: Path
    podcast_name: str
    episode_no: str
    title: str
    title_lines: list[str]
    guest: str
    host: str
    keywords: list[str]
    corrections: dict[str, str]
    banned_fragments: list[str]
    start: float
    duration: float
    stem: str
    work_dir: Path
    output_dir: Path
    style_dir: Path
    backgrounds: dict[str, Path]
    keep_post_farewell: bool


def run(command: list[str], cwd: Path | None = None, quiet: bool = False) -> None:
    kwargs = {}
    if quiet:
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    subprocess.run(command, cwd=cwd, check=True, **kwargs)


def probe_duration(path: Path) -> float:
    result = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        text=True,
    )
    return float(result.strip())


def parse_pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("correction must use WRONG=RIGHT")
    wrong, right = value.split("=", 1)
    if not wrong:
        raise argparse.ArgumentTypeError("correction source cannot be empty")
    return wrong, right


def merge_cli_list(cli_values: list[str] | None, metadata_value: object) -> list[str]:
    if cli_values:
        return cli_values
    if isinstance(metadata_value, list):
        return [str(item) for item in metadata_value if str(item).strip()]
    return []


def parse_corrections(value: object) -> dict[str, str]:
    """Accept a JSON object or the documented list of KEY=VALUE strings."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(key): str(replacement) for key, replacement in value.items()}
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        corrections: dict[str, str] = {}
        for item in value:
            wrong, right = parse_pair(item)
            corrections[wrong] = right
        return corrections
    raise ValueError("corrections must be an object or a list of KEY=VALUE strings")


def load_metadata(path: Path | None) -> dict:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_value(cli_value: object, metadata: dict, key: str, default: object = "") -> object:
    return cli_value if cli_value not in (None, "") else metadata.get(key, default)


def clean_title(title: str, episode_no: str) -> str:
    title = re.sub(rf"[-—_]\s*{re.escape(episode_no)}\s*$", "", title).strip()
    return re.sub(r"【[^】]*】\s*$", "", title).strip()


def get_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES[weight]:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    raise FileNotFoundError(f"No CJK {weight} font found; tried: {FONT_CANDIDATES[weight]}")


def font_name() -> str:
    return "Microsoft YaHei" if Path(r"C:\Windows\Fonts\msyh.ttc").exists() else "Noto Sans CJK SC"


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def split_text_by_width(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    draw = ImageDraw.Draw(Image.new("RGB", (16, 16)))
    if text_size(draw, text, font)[0] <= max_width:
        return [text]
    chunks: list[str] = []
    current = ""
    soft_breaks = "，。！？、；：,.;:!? "
    for char in text:
        candidate = current + char
        if current and text_size(draw, candidate, font)[0] > max_width:
            split_at = max((i + 1 for i, ch in enumerate(current) if ch in soft_breaks), default=-1)
            if split_at > 0:
                chunks.append(current[:split_at].strip())
                current = current[split_at:] + char
            else:
                chunks.append(current.strip())
                current = char
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    chunks = [chunk for chunk in chunks if chunk]

    # Greedy wrapping can leave a one-character flash at the end of a cue.
    # Move trailing characters forward until neighboring chunks are balanced,
    # while preserving the hard pixel-width limit for every subtitle line.
    for _ in range(len(chunks)):
        changed = False
        for index in range(len(chunks) - 1, 0, -1):
            left, right = chunks[index - 1], chunks[index]
            while len(left) > len(right) + 1:
                candidate_left = left[:-1].strip()
                candidate_right = (left[-1] + right).strip()
                if not candidate_left or text_size(draw, candidate_right, font)[0] > max_width:
                    break
                left, right = candidate_left, candidate_right
                changed = True
            chunks[index - 1], chunks[index] = left, right
        if not changed:
            break
    return chunks


def title_lines(ctx: Context, style: dict) -> list[str]:
    if ctx.title_lines:
        return ctx.title_lines[: style["title"].get("line_count", 2)]
    spec = style["title"]
    text = clean_title(ctx.title, ctx.episode_no)
    font = get_font("bold", spec["font_size"])
    lines = split_text_by_width(text, font, spec["max_width"])
    if len(lines) <= spec.get("line_count", 2):
        return lines
    midpoint = len(text) // 2
    candidates = [i for i in range(1, len(text)) if text[i - 1] in "，。！？：；"]
    split_at = min(candidates, key=lambda i: abs(i - midpoint)) if candidates else midpoint
    return [text[:split_at].strip(), text[split_at:].strip()]


def rounded(base: Image.Image, bbox: tuple[int, int, int, int], radius: int, fill, outline=None, width: int = 1) -> None:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(bbox, radius=radius, fill=fill, outline=outline, width=width)
    base.alpha_composite(layer)


def add_shadow(base: Image.Image, bbox: tuple[int, int, int, int], radius: int, spec: dict) -> None:
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    x1, y1, x2, y2 = bbox
    ox, oy = spec["offset"]
    ImageDraw.Draw(layer).rounded_rectangle(
        (x1 + ox, y1 + oy, x2 + ox, y2 + oy), radius=radius, fill=(35, 22, 12, spec["alpha"])
    )
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(spec["blur"])))


def add_cover(base: Image.Image, cover_path: Path, spec: dict) -> None:
    x, y, width, height = spec["x"], spec["y"], spec["width"], spec["height"]
    bbox = (x, y, x + width, y + height)
    if spec.get("shadow"):
        add_shadow(base, bbox, spec["radius"], spec["shadow"])
    image = ImageOps.fit(Image.open(cover_path).convert("RGBA"), (width, height), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width, height), radius=spec["radius"], fill=255)
    image.putalpha(mask)
    base.alpha_composite(image, (x, y))
    rounded(base, bbox, spec["radius"], (0, 0, 0, 0), (255, 255, 255, 80), 2)


def draw_lines(draw: ImageDraw.ImageDraw, lines: Iterable[str], x: int, y: int, font: ImageFont.FreeTypeFont, fill, gap: int) -> None:
    line_height = text_size(draw, "测试", font)[1] + gap
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height


def draw_chip_row(base: Image.Image, labels: Iterable[str], spec: dict, font: ImageFont.FreeTypeFont, colors: dict) -> None:
    draw = ImageDraw.Draw(base)
    start_x, x, y = spec["x"], spec["x"], spec["y"]
    sample_h = text_size(draw, "职业教育", font)[1]
    height = sample_h + spec["pad_y"] * 2
    for label in labels:
        width = text_size(draw, label, font)[0] + spec["pad_x"] * 2
        if x > start_x and x + width > start_x + spec["max_width"]:
            x = start_x
            y += height + spec["row_gap"]
        rounded(base, (x, y, x + width, y + height), height // 2, tuple(colors["chip_fill"]), tuple(colors["outline"]))
        label_h = text_size(draw, label, font)[1]
        draw.text((x + spec["pad_x"], y + (height - label_h) // 2 - 2), label, font=font, fill=tuple(colors["text"]) + (255,))
        x += width + spec["gap"]


def draw_horizontal_people(base: Image.Image, ctx: Context, style: dict) -> None:
    spec, colors = style["people_chips"], style["colors"]
    draw = ImageDraw.Draw(base)
    label_font = get_font("bold", spec["label_font_size"])
    value_font = get_font("bold", spec["value_font_size"])
    x, y = spec["x"], spec["y"]
    for label, value in [("嘉宾", ctx.guest), ("主播", ctx.host)]:
        label_w, label_h = text_size(draw, label, label_font)
        value_w, value_h = text_size(draw, value, value_font)
        width = 30 + label_w + 18 + value_w + 30
        rounded(base, (x, y, x + width, y + spec["height"]), spec["radius"], tuple(colors["chip_fill"]), tuple(colors["outline"]))
        draw.text((x + 30, y + (spec["height"] - label_h) // 2 - 1), label, font=label_font, fill=(70, 49, 37, 255))
        draw.text((x + 30 + label_w + 18, y + (spec["height"] - value_h) // 2 - 3), value, font=value_font, fill=tuple(colors["text"]) + (255,))
        x += width + spec["gap"]


def add_vertical_veil(base: Image.Image, style: dict) -> None:
    bg = style["background"]
    width, height = style["canvas"]["width"], style["canvas"]["height"]
    base.alpha_composite(Image.new("RGBA", (width, height), tuple(bg["warm_veil"])))
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    for y in range(height):
        top = max(0, bg["top_alpha"] - int(y * 0.12))
        bottom = max(0, int((y - bg["bottom_start"]) * 0.13))
        alpha = min(bg["bottom_alpha"], top + bottom)
        if alpha:
            draw.line((0, y, width, y), fill=tuple(bg["vignette"]) + (alpha,))
    base.alpha_composite(gradient)


def make_overlay(layout: str, ctx: Context, style: dict) -> Path:
    width, height = style["canvas"]["width"], style["canvas"]["height"]
    base = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    colors = style["colors"]
    if layout == "vertical":
        add_vertical_veil(base, style)
        card = style["main_card"]
        card_bbox = (card["x1"], card["y1"], card["x2"], card["y2"])
        add_shadow(base, card_bbox, card["radius"], card["shadow"])
        rounded(base, card_bbox, card["radius"], tuple(card["fill"]), tuple(card["outline"]), 2)
    draw = ImageDraw.Draw(base)
    ink = tuple(colors["text"]) + (255,)
    muted = tuple(colors["muted"]) + (215,)
    name = style["podcast_name"]
    draw.text((name["x"], name["y"]), ctx.podcast_name, font=get_font("bold", name["font_size"]), fill=ink)
    mark = style["episode_mark"]
    draw.text((mark["x"], mark["y"]), mark["template"].format(episode_no=ctx.episode_no), font=get_font("regular", mark["font_size"]), fill=muted)
    add_cover(base, ctx.cover, style["cover"])
    title = style["title"]
    draw_lines(draw, title_lines(ctx, style), title["x"], title["y"], get_font("bold", title["font_size"]), ink, title["line_gap"])
    if layout == "horizontal":
        draw_horizontal_people(base, ctx, style)
    else:
        people = style["people_chips"]
        draw_chip_row(base, [f"嘉宾  {ctx.guest}", f"主播  {ctx.host}"], people, get_font("bold", people["font_size"]), colors)
    keywords = style["keyword_chips"]
    draw_chip_row(base, ctx.keywords, keywords, get_font("bold", keywords["font_size"]), colors)
    box = style["subtitle_box"]
    bbox = (box["x1"], box["y1"], box["x2"], box["y2"])
    if box.get("shadow"):
        add_shadow(base, bbox, box["radius"], box["shadow"])
    rounded(base, bbox, box["radius"], tuple(box["fill"]), tuple(box["outline"]), 2)
    path = ctx.work_dir / f"{ctx.stem}_{layout}_overlay.png"
    base.save(path)
    return path


def parse_srt_time(value: str) -> float:
    hours, minutes, tail = value.strip().replace(".", ",").split(":")
    seconds, millis = tail.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def clean_caption(text: str, corrections: dict[str, str]) -> str:
    text = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", text))
    for wrong, right in corrections.items():
        text = text.replace(wrong, right)
    letters = sum(ch.isascii() and ch.isalpha() for ch in text)
    if letters >= 12 and letters / max(1, len(text)) > 0.6:
        return ""
    return text


def parse_srt(ctx: Context) -> list[Cue]:
    raw = ctx.srt.read_text(encoding="utf-8-sig")
    segment_end = ctx.start + ctx.duration
    cues: list[Cue] = []
    for block in re.split(r"\r?\n\s*\r?\n", raw.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing = next((line for line in lines if "-->" in line), "")
        if not timing:
            continue
        left, right = [part.strip().split()[0] for part in timing.split("-->", 1)]
        source_start, source_end = parse_srt_time(left), parse_srt_time(right)
        if source_end <= ctx.start or source_start >= segment_end:
            continue
        index = lines.index(timing)
        text = clean_caption("".join(lines[index + 1 :]), ctx.corrections)
        if not text or any(fragment.lower() in text.lower() for fragment in ctx.banned_fragments):
            continue
        start = max(source_start, ctx.start) - ctx.start
        end = min(source_end, segment_end) - ctx.start
        if text in {"拜拜", "谢谢"} and end - start > 6:
            end = start + 2.5
        cues.append(Cue(start, end, text))
    if ctx.keep_post_farewell:
        return cues
    farewell_end = None
    for cue in cues:
        if ctx.duration - cue.start <= 180 and any(word in cue.text for word in ["拜拜", "再见", "今天就在这"]):
            farewell_end = max(farewell_end or 0, cue.end + 0.5)
    return [cue for cue in cues if farewell_end is None or cue.start <= farewell_end]


def split_cues(cues: list[Cue], style: dict) -> list[Cue]:
    spec = style["subtitles"]
    font = get_font(spec["font_weight"], spec["font_size"])
    output: list[Cue] = []
    for cue in cues:
        chunks = split_text_by_width(cue.text, font, spec["max_width"])
        if len(chunks) == 1:
            output.append(cue)
            continue
        total = sum(len(chunk) for chunk in chunks)
        cursor = cue.start
        for index, chunk in enumerate(chunks):
            end = cue.end if index == len(chunks) - 1 else cursor + (cue.end - cue.start) * len(chunk) / total
            output.append(Cue(cursor, end, chunk))
            cursor = end
    return output


def make_ass(layout: str, ctx: Context, style: dict) -> Path:
    spec = style["subtitles"]
    primary = style["colors"]["text"]
    ass_color = f"&H00{primary[2]:02X}{primary[1]:02X}{primary[0]:02X}"
    bold = 1 if spec["font_weight"] == "bold" else 0
    width, height = style["canvas"]["width"], style["canvas"]["height"]
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "WrapStyle: 2", "ScaledBorderAndShadow: yes",
        f"PlayResX: {width}", f"PlayResY: {height}", "", "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font_name()},{spec['font_size']},{ass_color},&H000000FF,&H00000000,&H00000000,{bold},0,0,0,100,100,0,0,1,0,0,5,40,40,40,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    cx, cy = spec["center"]
    for cue in split_cues(parse_srt(ctx), style):
        text = cue.text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        lines.append(f"Dialogue: 0,{ass_time(cue.start)},{ass_time(cue.end)},Default,,0,0,0,,{{\\an5\\pos({cx},{cy})}}{text}")
    path = ctx.work_dir / f"{ctx.stem}_{layout}.ass"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def background_filter(style: dict, duration: float) -> str:
    canvas = style["canvas"]
    width, height, fps = canvas["width"], canvas["height"], canvas["fps"]
    value = f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},fps={fps}"
    if "saturation" in style["background"]:
        bg = style["background"]
        value += f",eq=saturation={bg['saturation']}:contrast={bg['contrast']}:brightness={bg['brightness']}"
    return f"{value},trim=duration={duration:.3f},setpts=PTS-STARTPTS"


def render_layout(layout: str, ctx: Context, style: dict, overlay: Path, ass: Path) -> Path:
    output = ctx.output_dir / f"{ctx.stem}_{layout}.mp4"
    filter_graph = f"[0:v]{background_filter(style, ctx.duration)}[bg];[bg][1:v]overlay=0:0:format=auto[v0];[v0]ass=filename='{ass.name}'[v]"
    command = [
        "ffmpeg", "-y", "-hide_banner", "-stream_loop", "-1", "-i", str(ctx.backgrounds[layout]),
        "-loop", "1", "-i", str(overlay), "-ss", f"{ctx.start:.3f}", "-i", str(ctx.audio),
        "-filter_complex", filter_graph, "-map", "[v]", "-map", "2:a:0", "-t", f"{ctx.duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
    ]
    run(command, cwd=ctx.work_dir)
    return output


def make_screenshots(video: Path, ctx: Context, layout: str) -> list[Path]:
    points = sorted({max(0.0, min(ctx.duration - 0.2, point)) for point in [1.0, ctx.duration / 2, ctx.duration - 1.0]})
    paths: list[Path] = []
    for index, point in enumerate(points, 1):
        path = ctx.output_dir / f"{ctx.stem}_{layout}_check_{index}.png"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{point:.3f}", "-i", str(video), "-frames:v", "1", "-update", "1", str(path)], quiet=True)
        paths.append(path)
    return paths


def load_style(ctx: Context, layout: str) -> dict:
    path = ctx.style_dir / f"style1-{layout}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def parse_layouts(value: str) -> list[str]:
    if value == "both":
        return ["horizontal", "vertical"]
    layouts = [item.strip() for item in value.split(",") if item.strip()]
    if not layouts or any(item not in {"horizontal", "vertical"} for item in layouts):
        raise ValueError("layout must be horizontal, vertical, or both")
    return layouts


def build_context(args: argparse.Namespace, layouts: list[str]) -> Context:
    metadata = load_metadata(args.metadata_json)
    audio = Path(args.audio)
    cover = Path(args.cover)
    srt = Path(args.srt)
    for path in [audio, cover, srt]:
        if not path.exists():
            raise FileNotFoundError(path)
    backgrounds: dict[str, Path] = {}
    for layout, cli_value, key in [
        ("horizontal", args.horizontal_bg_video, "horizontal_bg_video"),
        ("vertical", args.vertical_bg_video, "vertical_bg_video"),
    ]:
        value = resolve_value(cli_value, metadata, key)
        if layout in layouts:
            if not value:
                raise ValueError(f"{layout} background video is required")
            path = Path(str(value))
            if not path.exists():
                raise FileNotFoundError(path)
            backgrounds[layout] = path
    corrections = parse_corrections(metadata.get("corrections"))
    for wrong, right in args.correction:
        corrections[wrong] = right
    banned = list(dict.fromkeys(DEFAULT_BANNED + merge_cli_list(args.banned_fragment, metadata.get("banned_fragments"))))
    audio_duration = probe_duration(audio)
    start = max(0.0, args.start)
    requested = args.duration if args.duration is not None else audio_duration - start
    duration = min(requested, audio_duration - start)
    if duration <= 0:
        raise ValueError("start/duration is outside the audio")
    mode = args.mode
    if mode == "sample" and args.duration is None:
        duration = min(30.0, duration)
    work_dir, output_dir = args.work_dir.resolve(), args.output_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return Context(
        audio=audio.resolve(), cover=cover.resolve(), srt=srt.resolve(),
        podcast_name=str(resolve_value(args.podcast_name, metadata, "podcast_name", "播客")),
        episode_no=str(resolve_value(args.episode_no, metadata, "episode_no", "000")).zfill(3),
        title=str(resolve_value(args.title, metadata, "title", cover.stem)),
        title_lines=merge_cli_list(args.title_line, metadata.get("title_lines")),
        guest=str(resolve_value(args.guest, metadata, "guest", "嘉宾")),
        host=str(resolve_value(args.host, metadata, "host", "主播")),
        keywords=merge_cli_list(args.keyword, metadata.get("keywords")) or ["播客访谈", "真实故事", "生活观察"],
        corrections=corrections, banned_fragments=banned, start=start, duration=duration,
        stem=args.stem, work_dir=work_dir, output_dir=output_dir, style_dir=args.style_dir.resolve(),
        backgrounds=backgrounds, keep_post_farewell=args.keep_post_farewell_subtitles,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render style1 podcast videos over looping background clips.")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--cover", required=True)
    parser.add_argument("--srt", required=True)
    parser.add_argument("--horizontal-bg-video")
    parser.add_argument("--vertical-bg-video")
    parser.add_argument("--metadata-json", type=Path)
    parser.add_argument("--podcast-name")
    parser.add_argument("--episode-no")
    parser.add_argument("--title")
    parser.add_argument("--title-line", action="append")
    parser.add_argument("--guest")
    parser.add_argument("--host")
    parser.add_argument("--keyword", action="append")
    parser.add_argument("--correction", action="append", type=parse_pair, default=[])
    parser.add_argument("--banned-fragment", action="append")
    parser.add_argument("--keep-post-farewell-subtitles", action="store_true")
    parser.add_argument("--layout", default="both")
    parser.add_argument("--mode", choices=["sample", "full"], default="sample")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--stem", default="podcast_style1")
    parser.add_argument("--work-dir", type=Path, default=Path("video_work/style1"))
    parser.add_argument("--output-dir", type=Path, default=Path("video_outputs"))
    parser.add_argument("--style-dir", type=Path, default=DEFAULT_STYLE_DIR)
    args = parser.parse_args()

    layouts = parse_layouts(args.layout)
    ctx = build_context(args, layouts)
    manifest = {
        "style": "style1", "mode": args.mode, "audio": str(ctx.audio), "cover": str(ctx.cover),
        "srt": str(ctx.srt), "start": ctx.start, "duration": ctx.duration,
        "metadata": {"podcast_name": ctx.podcast_name, "episode_no": ctx.episode_no, "title": ctx.title, "title_lines": ctx.title_lines, "guest": ctx.guest, "host": ctx.host, "keywords": ctx.keywords},
        "corrections": ctx.corrections, "banned_fragments": ctx.banned_fragments, "layouts": {},
    }
    for layout in layouts:
        style = load_style(ctx, layout)
        overlay = make_overlay(layout, ctx, style)
        ass = make_ass(layout, ctx, style)
        video = render_layout(layout, ctx, style, overlay, ass)
        screenshots = make_screenshots(video, ctx, layout)
        manifest["layouts"][layout] = {
            "background": str(ctx.backgrounds[layout]), "style_config": str(ctx.style_dir / f"style1-{layout}.json"),
            "overlay": str(overlay), "ass": str(ass), "video": str(video), "screenshots": [str(path) for path in screenshots],
        }
        print(video)
    manifest_path = ctx.work_dir / f"{ctx.stem}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(manifest_path)


if __name__ == "__main__":
    main()
