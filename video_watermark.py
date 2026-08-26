"""
MERA PASHU MITRA  •  Video Watermark Engine (ffmpeg)
====================================================
- Logo har video frame par RIGHT side par overlay hota hai (transparent PNG).
- Portrait video (Shorts style)  → logo only, original resolution intact.
- Landscape video                → automatic 9:16 (1080x1920) conversion,
  upar/neeche blurred background ke saath — Shorts-ready, content crop nahi.
- Quality: H.264 CRF 20 (visually near-original), yuv420p (YouTube compatible),
  audio copy (AAC par zero loss), +faststart (WhatsApp instant play).

BLOCKING function — bot isse worker thread me chalata hai.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Optional

import config

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

INSTALL_HELP = (
    "ffmpeg install nahi hai. Install karo:\n"
    "• Ubuntu:  sudo apt install ffmpeg\n"
    "• Windows: winget install ffmpeg\n"
    "Phir bot dobara chala ke video bhejo."
)


class FFmpegMissingError(RuntimeError):
    pass


def _require_ffmpeg() -> None:
    if not FFMPEG or not FFPROBE:
        raise FFmpegMissingError(INSTALL_HELP)


@dataclass
class VideoJob:
    src: str
    dst: str
    logo_png: str                   # prepared transparent logo (video opacity baked)
    position: str                   # "top" | "mid" | "bottom"  (right side par)
    logo_width_frac: float          # video width ka fraction
    margin_frac: float              # edge se doori (width ka fraction)
    progress_cb: Optional[Callable[[int, int], None]] = None   # (done_sec, total_sec)


def probe_video(path: str) -> dict:
    """Duration, dimensions, audio codec — sab ek saath."""
    out = subprocess.run(
        [FFPROBE, "-v", "error",
         "-show_entries", "format=duration",
         "-show_entries", "stream=codec_type,codec_name,width,height",
         "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(out.stdout)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    return {
        "duration": float(data.get("format", {}).get("duration", 0) or 0),
        "width": v.get("width", 0) if v else 0,
        "height": v.get("height", 0) if v else 0,
        "has_audio": a is not None,
        "audio_codec": a.get("codec_name", "") if a else "",
    }


def _logo_y_expr(position: str, margin_expr: str) -> str:
    if position == "mid":
        return "(H-h)/2"
    if position == "bottom":
        return f"H-h-{margin_expr}"
    return margin_expr  # top (default)


def watermark_video(job: VideoJob) -> dict:
    """Video par right-side logo lagata hai (BLOCKING — worker thread me chalao).

    Returns: {"duration", "in_mb", "out_mb", "seconds", "was_landscape",
              "out_w", "out_h"}
    """
    _require_ffmpeg()
    t0 = time.time()
    info = probe_video(job.src)
    W, H = info["width"], info["height"]
    if W == 0 or H == 0:
        raise ValueError("Video stream nahi mili — file kharab lag rahi hai.")

    was_landscape = W > H
    base_w, out_h = (1080, 1920) if was_landscape else (W, H)
    out_w = base_w
    logo_px = max(32, round(base_w * job.logo_width_frac))   # logo width (pixels)

    margin = f"W*{job.margin_frac}"
    logo_x = f"W-w-{margin}"
    logo_y = _logo_y_expr(job.position, margin)
    logo_scale = f"[1:v]scale={logo_px}:-1[lgo];"

    if was_landscape:
        # 9:16 conversion: blurred background + centered original + logo
        vf = (
            "[0:v]split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=20[bg2];"
            "[fg]scale=1080:-2[fg2];"
            "[bg2][fg2]overlay=(W-w)/2:(H-h)/2[base];"
            f"{logo_scale}[base][lgo]overlay=x='{logo_x}':y='{logo_y}'[vout]"
        )
    else:
        vf = f"{logo_scale}[0:v][lgo]overlay=x='{logo_x}':y='{logo_y}'[vout]"

    # AAC audio ko copy (zero loss), baaki codecs ko AAC 192k me transcode
    audio_args = (
        ["-map", "0:a:0", "-c:a", "copy"]
        if info["has_audio"] and info["audio_codec"] == "aac"
        else (["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k"] if info["has_audio"] else [])
    )

    cmd = [
        FFMPEG, "-y", "-v", "error",
        "-i", job.src,
        "-i", job.logo_png,
        "-filter_complex", vf,
        "-map", "[vout]",
        *audio_args,
        "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        job.dst,
    ]

    total_sec = max(1, int(round(info["duration"])))
    last_report = -5.0

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        for line in proc.stdout:
            if line.startswith("out_time_ms=") and job.progress_cb:
                val = line.strip().split("=", 1)[1]
                if val not in ("N/A", ""):
                    sec = int(int(val) / 1000)
                    if sec - last_report >= 5:
                        last_report = sec
                        job.progress_cb(int(min(sec, total_sec)), total_sec)
        rc = proc.wait()
        err = proc.stderr.read()
    finally:
        if proc.poll() is None:
            proc.kill()

    if rc != 0 or not os.path.exists(job.dst):
        tail = "\n".join(err.splitlines()[-12:])
        raise RuntimeError(f"ffmpeg fail ho gaya:\n{tail}")

    return {
        "duration": round(info["duration"], 1),
        "in_mb": os.path.getsize(job.src) / 1048576,
        "out_mb": os.path.getsize(job.dst) / 1048576,
        "seconds": round(time.time() - t0, 1),
        "was_landscape": was_landscape,
        "out_w": out_w,
        "out_h": out_h,
    }
