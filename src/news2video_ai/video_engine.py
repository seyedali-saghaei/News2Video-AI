import argparse
import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

# =========================================================
# COMMON
# =========================================================

def resolve_executable(environment_key: str, executable: str) -> str:
    """Resolve an FFmpeg executable from an environment override or PATH."""
    configured = os.getenv(environment_key)
    if configured:
        return configured

    discovered = shutil.which(executable)
    if discovered:
        return discovered

    raise FileNotFoundError(
        f"{executable} was not found. Install FFmpeg or set {environment_key}."
    )


def resolve_fonts_directory() -> Path | None:
    """Return an optional font directory for FFmpeg's subtitles filter."""
    configured = os.getenv("NEWS2VIDEO_FONTS_DIR")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_dir():
            raise FileNotFoundError(f"Font directory not found: {path}")
        return path

    windows_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    return windows_fonts if windows_fonts.is_dir() else None

def run_command(command: list[str]) -> None:
    print("\nRunning command:")
    print(" ".join(command))

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if process.returncode != 0:
        print(process.stderr, file=sys.stderr)
        raise RuntimeError(
            f"Command failed with exit code {process.returncode}"
        )

    print(process.stderr)


def ensure_file_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"{label} not found: {path}"
        )


# =========================================================
# AUDIO
# =========================================================

def get_audio_duration(audio_path: Path) -> float:
    ensure_file_exists(audio_path, "Audio")

    command = [
        resolve_executable("FFPROBE_PATH", "ffprobe"),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if process.returncode != 0:
        raise RuntimeError(
            f"FFprobe failed: {process.stderr}"
        )

    try:
        duration = float(
            process.stdout.strip()
        )
    except ValueError as error:
        raise RuntimeError(
            f"Could not read audio duration: {process.stdout}"
        ) from error

    if duration <= 0:
        raise RuntimeError(
            f"Invalid audio duration: {duration}"
        )

    return duration


# =========================================================
# SUBTITLE
# =========================================================

def decode_base64_text(encoded_text: str) -> str:
    try:
        decoded_bytes = base64.b64decode(
            encoded_text
        )

        return decoded_bytes.decode(
            "utf-8"
        ).strip()

    except Exception as error:
        raise ValueError(
            "Subtitle Base64 could not be decoded."
        ) from error


def escape_ass_text(text: str) -> str:
    return (
        text
        .replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r\n", r"\N")
        .replace("\n", r"\N")
    )


def seconds_to_ass_time(
    seconds: float
) -> str:
    total_centiseconds = int(
        round(seconds * 100)
    )

    hours = (
        total_centiseconds // 360000
    )

    remaining = (
        total_centiseconds % 360000
    )

    minutes = remaining // 6000
    remaining %= 6000

    secs = remaining // 100
    centiseconds = remaining % 100

    return (
        f"{hours}:"
        f"{minutes:02d}:"
        f"{secs:02d}."
        f"{centiseconds:02d}"
    )


def create_ass_subtitle(
    subtitle_path: Path,
    subtitle_text: str,
    duration: float,
    width: int,
    height: int,
) -> None:

    safe_text = escape_ass_text(
        subtitle_text
    )

    end_time = seconds_to_ass_time(
        duration
    )

    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Persian,Vazirmatn,64,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,2,80,80,135,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{end_time},Persian,,0,0,0,,{{\\q0}}{safe_text}
"""

    subtitle_path.write_text(
        ass_content,
        encoding="utf-8-sig",
    )


# =========================================================
# FFMPEG FILTER
# =========================================================

def escape_ffmpeg_filter_path(
    path: Path
) -> str:

    normalized = (
        path
        .resolve()
        .as_posix()
    )

    return normalized.replace(
        ":",
        r"\:"
    )


def build_video_filter(
    subtitle_path: Path,
    width: int,
    height: int,
    fps: int,
    duration: float,
) -> str:

    fade_duration = min(
        1.0,
        duration / 4
    )

    fade_out_start = max(
        0.0,
        duration - fade_duration
    )

    subtitle_filter_path = (
        escape_ffmpeg_filter_path(
            subtitle_path
        )
    )

    fonts_directory = resolve_fonts_directory()

    large_width = int(
        width * 1.25
    )

    large_height = int(
        height * 1.25
    )

    filters = [

        (
            f"scale="
            f"{large_width}:"
            f"{large_height}:"
            f"force_original_aspect_ratio=increase"
        ),

        (
            f"crop="
            f"{large_width}:"
            f"{large_height}"
        ),

        (
            f"zoompan="
            f"z='min(max(pzoom,1.0)+0.0015,1.12)':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d=1:"
            f"s={width}x{height}:"
            f"fps={fps}"
        ),

        (
            f"subtitles=filename='{subtitle_filter_path}'"
            + (
                f":fontsdir='{escape_ffmpeg_filter_path(fonts_directory)}'"
                if fonts_directory
                else ""
            )
        ),

        (
            f"fade="
            f"t=in:"
            f"st=0:"
            f"d={fade_duration:.3f}:"
            f"color=black"
        ),

        (
            f"fade="
            f"t=out:"
            f"st={fade_out_start:.3f}:"
            f"d={fade_duration:.3f}:"
            f"color=black"
        ),

        "format=yuv420p",
    ]

    return ",".join(filters)


# =========================================================
# RENDER SCENE
# =========================================================

def render_scene(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    subtitle_text: str,
    width: int,
    height: int,
    fps: int,
) -> None:

    ensure_file_exists(
        image_path,
        "Image"
    )

    ensure_file_exists(
        audio_path,
        "Audio"
    )

    if not subtitle_text:
        raise ValueError(
            "Subtitle text is empty."
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    audio_duration = (
        get_audio_duration(
            audio_path
        )
    )

    print(
        f"Audio duration: "
        f"{audio_duration:.3f} seconds"
    )

    subtitle_path = (
        output_path.with_suffix(
            ".ass"
        )
    )

    create_ass_subtitle(
        subtitle_path=subtitle_path,
        subtitle_text=subtitle_text,
        duration=audio_duration,
        width=width,
        height=height,
    )

    video_filter = (
        build_video_filter(
            subtitle_path=subtitle_path,
            width=width,
            height=height,
            fps=fps,
            duration=audio_duration,
        )
    )

    command = [
        resolve_executable("FFMPEG_PATH", "ffmpeg"),
        "-y",

        "-loop",
        "1",

        "-framerate",
        str(fps),

        "-i",
        str(image_path),

        "-i",
        str(audio_path),

        "-t",
        f"{audio_duration:.3f}",

        "-vf",
        video_filter,

        "-c:v",
        "libx264",

        "-preset",
        "medium",

        "-crf",
        "20",

        "-c:a",
        "aac",

        "-b:a",
        "192k",

        "-ar",
        "48000",

        "-ac",
        "2",

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        "-r",
        str(fps),

        str(output_path),
    ]

    run_command(
        command
    )

    if not output_path.exists():
        raise RuntimeError(
            "Output video was not created."
        )

    file_size = (
        output_path
        .stat()
        .st_size
    )

    if file_size < 100_000:
        raise RuntimeError(
            f"Output video is suspiciously small: "
            f"{file_size} bytes"
        )

    print(
        f"\nScene created successfully:"
        f"\n{output_path}"
    )


# =========================================================
# NORMALIZE
# =========================================================

def normalize_video(
    input_path: Path,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
) -> None:

    ensure_file_exists(
        input_path,
        "Video"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        resolve_executable("FFMPEG_PATH", "ffmpeg"),
        "-y",

        "-i",
        str(input_path),

        "-vf",
        f"scale={width}:{height},fps={fps}",

        "-c:v",
        "libx264",

        "-preset",
        "medium",

        "-crf",
        "20",

        "-c:a",
        "aac",

        "-ar",
        "48000",

        "-ac",
        "2",

        "-b:a",
        "192k",

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    run_command(
        command
    )


# =========================================================
# MERGE
# =========================================================

def merge_videos(
    video_paths: list[Path],
    output_path: Path,
) -> None:

    for video_path in video_paths:
        ensure_file_exists(
            video_path,
            "Video"
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    concat_file = (
        output_path.parent
        / f"{output_path.stem}_concat.txt"
    )

    lines = []

    for video_path in video_paths:

        safe_path = (
            video_path
            .resolve()
            .as_posix()
        )

        lines.append(
            f"file '{safe_path}'"
        )

    concat_file.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    command = [
        resolve_executable("FFMPEG_PATH", "ffmpeg"),
        "-y",

        "-f",
        "concat",

        "-safe",
        "0",

        "-i",
        str(concat_file),

        "-c",
        "copy",

        str(output_path),
    ]

    run_command(
        command
    )

    if not output_path.exists():
        raise RuntimeError(
            "Merged video was not created."
        )


# =========================================================
# FINAL VIDEO
# =========================================================

def create_final_video(
    scene_paths: list[Path],
    intro_path: Path,
    outro_path: Path,
    output_path: Path,
    width: int,
    height: int,
    fps: int,
) -> None:

    print(
        "\n=== FINALIZE VIDEO ==="
    )

    if not scene_paths:
        raise ValueError(
            "No scenes provided."
        )

    work_dir = (
        output_path.parent
    )

    work_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    ensure_file_exists(
        intro_path,
        "Intro"
    )

    ensure_file_exists(
        outro_path,
        "Outro"
    )

    for scene in scene_paths:
        ensure_file_exists(
            scene,
            "Scene"
        )

    # -----------------------------------
    # 1. Merge scenes
    # -----------------------------------

    news_raw = (
        work_dir
        / "news_raw.mp4"
    )

    print(
        "\n[1/5] Merging scenes..."
    )

    merge_videos(
        video_paths=scene_paths,
        output_path=news_raw,
    )

    # -----------------------------------
    # 2. Normalize news
    # -----------------------------------

    news_normalized = (
        work_dir
        / "news_normalized.mp4"
    )

    print(
        "\n[2/5] Normalizing news..."
    )

    normalize_video(
        input_path=news_raw,
        output_path=news_normalized,
        width=width,
        height=height,
        fps=fps,
    )

    # -----------------------------------
    # 3. Normalize intro
    # -----------------------------------

    intro_normalized = (
        work_dir
        / "intro_normalized.mp4"
    )

    print(
        "\n[3/5] Normalizing intro..."
    )

    normalize_video(
        input_path=intro_path,
        output_path=intro_normalized,
        width=width,
        height=height,
        fps=fps,
    )

    # -----------------------------------
    # 4. Normalize outro
    # -----------------------------------

    outro_normalized = (
        work_dir
        / "outro_normalized.mp4"
    )

    print(
        "\n[4/5] Normalizing outro..."
    )

    normalize_video(
        input_path=outro_path,
        output_path=outro_normalized,
        width=width,
        height=height,
        fps=fps,
    )

    # -----------------------------------
    # 5. Final merge
    # -----------------------------------

    print(
        "\n[5/5] Creating final video..."
    )

    merge_videos(
        video_paths=[
            intro_normalized,
            news_normalized,
            outro_normalized,
        ],
        output_path=output_path,
    )

    print(
        "\n=================================="
    )

    print(
        "FINAL VIDEO CREATED SUCCESSFULLY"
    )

    print(
        output_path
    )

    print(
        "=================================="
    )


# =========================================================
# CLI
# =========================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "News2Video AI video engine"
        )
    )

    subparsers = (
        parser.add_subparsers(
            dest="mode",
            required=True,
        )
    )

    # =====================================================
    # MODE 1: render-scene
    # =====================================================

    scene_parser = (
        subparsers.add_parser(
            "render-scene",
            help="Render one news scene",
        )
    )

    scene_parser.add_argument(
        "--image",
        required=True,
    )

    scene_parser.add_argument(
        "--audio",
        required=True,
    )

    scene_parser.add_argument(
        "--output",
        required=True,
    )

    scene_parser.add_argument(
        "--subtitle-base64",
        required=True,
    )

    scene_parser.add_argument(
        "--width",
        type=int,
        default=1080,
    )

    scene_parser.add_argument(
        "--height",
        type=int,
        default=1920,
    )

    scene_parser.add_argument(
        "--fps",
        type=int,
        default=30,
    )

    # =====================================================
    # MODE 2: finalize-video
    # =====================================================

    final_parser = (
        subparsers.add_parser(
            "finalize-video",
            help=(
                "Merge scenes with intro "
                "and outro"
            ),
        )
    )

    final_parser.add_argument(
        "--scenes",
        nargs="+",
        required=True,
        help=(
            "List of scene MP4 files"
        ),
    )

    final_parser.add_argument(
        "--intro",
        required=True,
    )

    final_parser.add_argument(
        "--outro",
        required=True,
    )

    final_parser.add_argument(
        "--output",
        required=True,
    )

    final_parser.add_argument(
        "--width",
        type=int,
        default=1080,
    )

    final_parser.add_argument(
        "--height",
        type=int,
        default=1920,
    )

    final_parser.add_argument(
        "--fps",
        type=int,
        default=30,
    )

    args = parser.parse_args()

    try:

        # =============================================
        # render-scene
        # =============================================

        if args.mode == "render-scene":

            subtitle_text = (
                decode_base64_text(
                    args.subtitle_base64
                )
            )

            render_scene(
                image_path=Path(
                    args.image
                ),
                audio_path=Path(
                    args.audio
                ),
                output_path=Path(
                    args.output
                ),
                subtitle_text=subtitle_text,
                width=args.width,
                height=args.height,
                fps=args.fps,
            )

        # =============================================
        # finalize-video
        # =============================================

        elif args.mode == "finalize-video":

            create_final_video(
                scene_paths=[
                    Path(scene)
                    for scene
                    in args.scenes
                ],
                intro_path=Path(
                    args.intro
                ),
                outro_path=Path(
                    args.outro
                ),
                output_path=Path(
                    args.output
                ),
                width=args.width,
                height=args.height,
                fps=args.fps,
            )

    except Exception as error:

        print(
            f"\nERROR: {error}",
            file=sys.stderr,
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
