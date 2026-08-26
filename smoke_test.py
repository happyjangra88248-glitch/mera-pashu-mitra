"""
Smoke test — Telegram ke bina watermark engine ka poora flow test karta hai.

Run:  python smoke_test.py

Yeh test_assets/ me fake yellow-background MPM logo + fake vet-notes PDF
banata hai, uspar watermark lagata hai, size report karta hai, aur pehle
page ka preview render karke nazar se check karne ko deta hai.
"""

from __future__ import annotations

import os

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from PIL import Image, ImageDraw, ImageFont

import config
from watermark import WatermarkJob, prepare_logo, watermark_pdf

BASE = os.path.dirname(os.path.abspath(__file__))
TEST_DIR = os.path.join(BASE, "test_assets")
os.makedirs(TEST_DIR, exist_ok=True)
os.makedirs(config.OUTPUT_DIR, exist_ok=True)


def _find_font(size: int):
    for cand in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        if os.path.exists(cand):
            return ImageFont.truetype(cand, size)
    return ImageFont.load_default()


def make_fake_logo(path: str) -> None:
    """Yellow background wala MPM-style logo (aapke logo jaisa scenario)."""
    img = Image.new("RGB", (500, 500), (255, 212, 0))          # flat yellow background
    d = ImageDraw.Draw(img)
    d.ellipse((70, 70, 430, 430), fill=(121, 85, 72))          # brown circle
    d.text((250, 215), "MPM", font=_find_font(90), fill=(255, 212, 0), anchor="mm")
    d.text((250, 330), "MERA PASHU MITRA", font=_find_font(28), fill=(255, 244, 194), anchor="mm")
    img.save(path, "PNG")
    print(f"[test] fake logo → {path}")


def make_fake_pdf(path: str, pages: int = 3) -> None:
    doc = fitz.open()
    content = [
        ("Vet Anatomy — Day 1", [
            "MUSCLE OF LOCOMOTION",
            "- Biceps femoris: origin, insertion, action",
            "- Gastrocnemius: common laceration sites",
            "Clinical note: always palpate before injection.",
        ]),
        ("Pharmacology — Antibiotics", [
            "Tetracyclines: spectrum and side effects",
            "- Do NOT give to calves under 8 weeks",
            "Dose: 10-20 mg/kg PO q12h",
        ]),
        ("Dairy Ruminant Diseases", [
            "Rinderpest vs FMD — differential table",
            "- Fever plus vesicles = FMD till proven otherwise",
            "Reporting: notifiable disease protocol",
        ]),
    ][:pages]
    for title, lines in content:
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((50, 70), title, fontsize=20, fontname="helv")
        y = 120
        for ln in lines:
            page.insert_text((50, y), ln, fontsize=12, fontname="helv")
            y += 30
    doc.save(path)
    doc.close()
    print(f"[test] fake PDF → {path} ({pages} pages)")


def main() -> None:
    src = os.path.join(TEST_DIR, "sample_notes.pdf")
    out = os.path.join(config.OUTPUT_DIR, "SMOKE_TEST_watermarked.pdf")

    # Real logo ho to wahi use karo, warna fake yellow logo banao
    real_logo = os.path.join(config.BASE_DIR, "assets", "logo.png")
    if os.path.exists(real_logo):
        logo_path = real_logo
        print("[test] real assets/logo.png use kar rahe hain (permanent logo)")
    else:
        logo_path = os.path.join(TEST_DIR, "logo.png")
        make_fake_logo(logo_path)
    config.LOGO_PATH = logo_path
    make_fake_pdf(src, pages=3)

    in_mb = os.path.getsize(src) / 1048576
    prepared = prepare_logo(config.CENTER_OPACITY)
    with Image.open(prepared) as im:
        print(f"[test] prepared logo: {im.width}x{im.height}, mode={im.mode}")

    job = WatermarkJob(
        src=src, dst=out, logo_png=prepared, mode="center",
        logo_width_frac=config.CENTER_LOGO_WIDTH,
        margin_frac=config.CORNER_MARGIN,
        progress_cb=lambda d, t: print(f"[test] page {d}/{t}"),
    )
    res = watermark_pdf(job)
    out_mb = os.path.getsize(out) / 1048576
    print(f"[test] result: {res['pages']} pages, {in_mb:.3f} MB → {out_mb:.3f} MB, {res['seconds']}s")

    # Pehle page ka visual preview (nazar se check: text saaf + watermark faint)
    prev = os.path.join(config.OUTPUT_DIR, "preview_page1.png")
    d = fitz.open(out)
    d[0].get_pixmap(dpi=110).save(prev)
    d.close()
    print(f"[test] preview → {prev}")
    print("✅ SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
