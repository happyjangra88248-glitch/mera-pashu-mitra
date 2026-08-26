"""
MERA PASHU MITRA  •  Watermark Engine
=====================================
- Logo preparation: automatic background removal (yellow/white/whatever
  flat color, edges se flood-fill — logo ke ANDAR ka same color safe rehta
  hai), downscale, aur opacity baking.
- PDF stamping: PyMuPDF se per-page VECTOR-PRESERVING watermark.
  Page ka text layer kabhi rasterize nahi hota  →  file size low rehta hai
  aur text search/copy karne layak rehta hai (exam notes ke liye zaroori).

Sab functions BLOCKING hain — bot inhe worker thread me chalata hai
(asyncio.to_thread), taaki Telegram event loop kabhi freeze na ho.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageFilter

# PyMuPDF: naye versions me `import pymupdf`, purane me `import fitz`
try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover (purane versions ke liye)
    import fitz  # type: ignore

import config


# ----------------------------------------------------------------------
# Logo preparation
# ----------------------------------------------------------------------

def _remove_edge_background(img: Image.Image, tolerance: int) -> Image.Image:
    """Sirf image ke EDGES se connected background pixels transparent karta hai.

    Isliye logo ke andar ka same color (jaise MPM logo ke andar ka yellow
    shape) safe rehta hai — sirf bahar ka flat background jaata hai.
    """
    arr = np.asarray(img, dtype=np.int16)
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3]

    # Background color = chaaron corners ke pixels ka median
    p = max(2, min(h, w) // 15)
    patches = [rgb[:p, :p], rgb[:p, -p:], rgb[-p:, :p], rgb[-p:, -p:]]
    bg = np.median(np.concatenate([x.reshape(-1, 3) for x in patches], axis=0), axis=0)

    is_bg = np.abs(rgb - bg).max(axis=2) <= tolerance

    # BFS flood fill, starting from har border pixel
    visited = np.zeros((h, w), dtype=bool)
    dq: deque = deque()

    def seed(y: int, x: int) -> None:
        if is_bg[y, x] and not visited[y, x]:
            visited[y, x] = True
            dq.append((y, x))

    for x in range(w):
        seed(0, x)
        seed(h - 1, x)
    for y in range(h):
        seed(y, 0)
        seed(y, w - 1)

    while dq:
        y, x = dq.popleft()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and is_bg[ny, nx] and not visited[ny, nx]:
                visited[ny, nx] = True
                dq.append((ny, nx))

    arr[visited, 3] = 0
    out = Image.fromarray(arr.astype(np.uint8), "RGBA")

    # Edge ko 1px andar kheencho (JPEG/edge halo na bane), phir thoda soft karo
    r, g, b, a = out.split()
    a = a.filter(ImageFilter.MinFilter(3))
    a = a.filter(ImageFilter.GaussianBlur(0.6))
    return Image.merge("RGBA", (r, g, b, a))


def _has_transparent_border(img: Image.Image) -> bool:
    """Logo already transparent hai to background removal skip karo."""
    a = np.asarray(img, dtype=np.uint8)[:, :, 3]
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return float(np.median(border)) < 10.0


def prepare_logo(opacity: float) -> str:
    """Logo ko embed-ready PNG banata hai: transparent + chhota + opacity baked.

    Cache: logo file ya opacity badle to re-process, warna cache use hoti hai.
    Returns: prepared PNG ka path.
    """
    if not os.path.exists(config.LOGO_PATH):
        raise FileNotFoundError(
            f"Logo nahi mila: {config.LOGO_PATH}\n"
            "assets/logo.png par apna logo PNG file ke roop me rakhein."
        )

    cache_dir = os.path.join(config.OUTPUT_DIR, ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, f"logo_{opacity:.2f}.png")
    stamp = cache + ".mtime"

    mtime = os.path.getmtime(config.LOGO_PATH)
    if os.path.exists(cache) and os.path.exists(stamp):
        try:
            if float(open(stamp).read().strip()) == mtime:
                return cache
        except ValueError:
            pass

    img = Image.open(config.LOGO_PATH).convert("RGBA")

    if _has_transparent_border(img):
        print("[logo] already transparent — background removal skipped")
    else:
        print(f"[logo] removing background (tolerance={config.BG_TOLERANCE}) ...")
        img = _remove_edge_background(img, config.BG_TOLERANCE)

    # Embed-size ke liye downscale (400px ka logo 300 pages par bhi negligible rehta hai)
    if img.width > config.LOGO_MAX_PX_WIDTH:
        ratio = config.LOGO_MAX_PX_WIDTH / img.width
        img = img.resize(
            (config.LOGO_MAX_PX_WIDTH, max(1, round(img.height * ratio))),
            Image.LANCZOS,
        )

    # Opacity ko alpha channel me BAKE karo — har PDF viewer par same look
    r, g, b, a = img.split()
    a = a.point(lambda v: round(v * opacity))
    img = Image.merge("RGBA", (r, g, b, a))

    img.save(cache, "PNG")
    with open(stamp, "w") as fh:
        fh.write(str(mtime))
    print(f"[logo] ready → {img.width}x{img.height} px, opacity={opacity}")
    return cache


# ----------------------------------------------------------------------
# PDF watermarking
# ----------------------------------------------------------------------

@dataclass
class WatermarkJob:
    src: str                                   # input PDF path
    dst: str                                   # output PDF path
    logo_png: str                              # prepared (transparent) logo path
    mode: str                                  # "center" | "corner"
    logo_width_frac: float                     # page width ka fraction
    margin_frac: float = 0.035                 # corner mode me
    progress_cb: Optional[Callable[[int, int], None]] = None   # (done, total)


def _target_rect(page_rect, mode: str, logo_aspect: float,
                 width_frac: float, margin_frac: float):
    """Per-page watermark rectangle (isliye mixed portrait/landscape pages
    bhi sahi handle hote hain). logo_aspect = width / height."""
    w, h = page_rect.width, page_rect.height
    tw = w * width_frac
    th = tw / logo_aspect
    max_th = h * 0.25                          # height hard-cap: text ko chhipe nahi
    if th > max_th:
        th = max_th
        tw = th * logo_aspect

    if mode == "corner":
        m = w * margin_frac
        return fitz.Rect(
            page_rect.x1 - tw - m,
            page_rect.y1 - th - m,
            page_rect.x1 - m,
            page_rect.y1 - m,
        )
    cx = (page_rect.x0 + page_rect.x1) / 2
    cy = (page_rect.y0 + page_rect.y1) / 2
    return fitz.Rect(cx - tw / 2, cy - th / 2, cx + tw / 2, cy + th / 2)


def watermark_pdf(job: WatermarkJob) -> dict:
    """Poore PDF par watermark lagata hai.

    BLOCKING function — hamesha worker thread me chalu karein.
    Returns: {"pages", "in_mb", "out_mb", "seconds"}
    """
    t0 = time.time()
    doc = fitz.open(job.src)
    if doc.needs_pass:
        doc.close()
        raise PermissionError("PDF password-protected hai — password hata ke dobara bhejo.")

    total = len(doc)
    if total == 0:
        doc.close()
        raise ValueError("PDF me koi page nahi mila.")

    with Image.open(job.logo_png) as logo_img:
        logo_aspect = logo_img.width / logo_img.height

    pm = fitz.Pixmap(job.logo_png)             # RGBA PNG → alpha SMask ke roop me embed

    try:
        for i, page in enumerate(doc):
            rect = _target_rect(page.rect, job.mode, logo_aspect,
                                job.logo_width_frac, job.margin_frac)
            page.insert_image(rect, pixmap=pm, overlay=True)
            if job.progress_cb and (i % 25 == 0 or i == total - 1):
                job.progress_cb(i + 1, total)

        # garbage=4 → duplicate streams/images bhi hata deta hai (size bachat)
        doc.save(job.dst, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
        del pm

    return {
        "pages": total,
        "in_mb": os.path.getsize(job.src) / 1048576,
        "out_mb": os.path.getsize(job.dst) / 1048576,
        "seconds": round(time.time() - t0, 1),
    }
