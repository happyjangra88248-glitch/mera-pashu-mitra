"""
MERA PASHU MITRA  •  Telegram Watermark Bot (aiogram 3)
=======================================================
Run (VS Code terminal, project folder se):
    python bot.py

Flow: aap PDF bhejo  →  bot logo laga ke optimized PDF wapas de deta hai.
Logo project me assets/logo.png par hai — bhejne ki zaroorat nahi.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import uuid

# PyMuPDF: naye versions me `import pymupdf`, purane me `import fitz`
try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent, FSInputFile, Message

import config
from watermark import WatermarkJob, prepare_logo, watermark_pdf
from video_watermark import (
    FFmpegMissingError,
    INSTALL_HELP,
    VideoJob,
    probe_video,
    watermark_video,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("mpm")

WORKDIR = os.path.join(config.BASE_DIR, "tmp")
os.makedirs(WORKDIR, exist_ok=True)
os.makedirs(config.OUTPUT_DIR, exist_ok=True)

router = Router()
state = {
    "mode": "center",
    "vpos": "top",
    "vsize": config.VIDEO_LOGO_WIDTH,   # runtime par /vsize se badla ja sakta hai
    "busy": False,
}

VSIZE_PRESETS = {"small": 0.12, "medium": 0.16, "large": 0.20}

WELCOME = (
    "🐄🐐 <b>Mera Pashu Mitra — Watermark Bot</b>\n\n"
    "📥 <b>PDF bhejo</b> → har page par MPM logo, optimized PDF wapas\n"
    "🎬 <b>Video bhejo</b> → right side par MPM logo, Shorts-ready video wapas\n\n"
    "🎛️ <b>Commands:</b>\n"
    "/mode center — PDF logo beech me, halka (default)\n"
    "/mode corner — PDF logo bottom-right, chhota saaf\n"
    "/vpos top — video logo upar-right (default)\n"
    "/vpos mid — video logo right me beech\n"
    "/vpos bottom — video logo neeche-right\n"
    "/vsize small | medium | large — video logo ki size\n"
    "/help — yeh message\n\n"
    "⚠️ PDF password-protected NA ho.\n"
    f"⚠️ Max ~{config.MAX_INPUT_MB} MB file (Telegram API limit)."
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id in config.ADMIN_IDS


def _mode_cfg():
    """(opacity, logo_width_frac, margin_frac) current PDF mode ke liye."""
    if state["mode"] == "corner":
        return config.CORNER_OPACITY, config.CORNER_LOGO_WIDTH, config.CORNER_MARGIN
    return config.CENTER_OPACITY, config.CENTER_LOGO_WIDTH, config.CORNER_MARGIN


def _size_limit_mb(kind: str) -> float:
    """Standard API: 19 MB. Local Bot API on ho: 1900 MB."""
    if config.USE_LOCAL_API:
        return 1900.0
    return config.MAX_INPUT_MB if kind == "pdf" else config.MAX_VIDEO_MB


def _sanitize_stem(name: str) -> str:
    stem = os.path.splitext(os.path.basename(name or "notes"))[0]
    stem = re.sub(r"[^\w\- ]", "", stem, flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", stem)[:60] or "notes"


def _optional_qpdf(path: str) -> bool:
    """qpdf installed ho toh ek structural dedupe/compression pass (optional).
    Install: sudo apt install qpdf  (na ho toh bot khud skip kar deta hai)."""
    if shutil.which("qpdf") is None:
        return False
    tmp = path + ".qpdf"
    try:
        subprocess.run(
            ["qpdf", "--object-streams=generate", "--compress-streams=y", path, tmp],
            check=True, timeout=180,
        )
        if os.path.getsize(tmp) < os.path.getsize(path):
            os.replace(tmp, path)
            return True
        os.remove(tmp)
    except Exception as e:
        log.warning("qpdf pass failed (skip kar rahe hain): %s", e)
        if os.path.exists(tmp):
            os.remove(tmp)
    return False


async def _safe_edit(msg: Message, text: str) -> None:
    try:
        await msg.edit_text(text)
    except TelegramBadRequest:
        pass  # flood limit / "message not modified" — ignore
    except Exception:
        log.exception("status update failed")


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------

@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    if user is None:
        return
    if not config.ADMIN_IDS:
        await message.answer(
            f"⚙️ Pehla setup step: aapka Telegram ID hai <b>{user.id}</b>\n"
            "Ise config.py me ADMIN_IDS set karo, phir bot dobara chala ke /start bhejo."
        )
        return
    if not _is_admin(message):
        log.info("Unauthorized /start from %s (@%s)", user.id, user.username)
        await message.answer("⛔ Yeh bot private hai.")
        return
    cur = "center (halka, beech me)" if state["mode"] == "center" else "corner (bottom-right)"
    await message.answer(WELCOME + f"\n\n🔖 Current mode: <b>{cur}</b>")


@router.message(Command("help"))
async def cmd_help(message: Message):
    await cmd_start(message)


@router.message(Command("mode"))
async def cmd_mode(message: Message):
    if not config.ADMIN_IDS or not _is_admin(message):
        await message.answer("⛔ Yeh bot private hai.")
        return
    parts = (message.text or "").split()
    if len(parts) >= 2 and parts[1].lower() in ("center", "corner"):
        state["mode"] = parts[1].lower()
        cur = "center (halka, beech me)" if state["mode"] == "center" else "corner (bottom-right)"
        await message.answer(f"✅ Watermark mode: <b>{cur}</b>")
    else:
        await message.answer("Usage: <code>/mode center</code>  ya  <code>/mode corner</code>")


@router.message(Command("vpos"))
async def cmd_vpos(message: Message):
    """Video logo ki position (hamesha right side par)."""
    if not config.ADMIN_IDS or not _is_admin(message):
        await message.answer("⛔ Yeh bot private hai.")
        return
    parts = (message.text or "").split()
    labels = {
        "top": "upar-right (default — Shorts ke liye safest)",
        "mid": "right side, beech me",
        "bottom": "neeche-right",
    }
    if len(parts) >= 2 and parts[1].lower() in labels:
        state["vpos"] = parts[1].lower()
        await message.answer(f"✅ Video logo position: <b>{labels[state['vpos']]}</b>")
    else:
        await message.answer(
            "Usage: <code>/vpos top</code> | <code>/vpos mid</code> | <code>/vpos bottom</code>"
        )


@router.message(Command("vsize"))
async def cmd_vsize(message: Message):
    """Video logo ki size: small / medium / large."""
    if not config.ADMIN_IDS or not _is_admin(message):
        await message.answer("⛔ Yeh bot private hai.")
        return
    parts = (message.text or "").split()
    if len(parts) >= 2 and parts[1].lower() in VSIZE_PRESETS:
        state["vsize"] = VSIZE_PRESETS[parts[1].lower()]
        await message.answer(
            f"✅ Video logo size: <b>{parts[1].lower()}</b> "
            f"({state['vsize']:.0%} of video width)\n"
            "Agla bheja video isi size par watermark hoga."
        )
    else:
        await message.answer(
            "Usage: <code>/vsize small</code> | <code>/vsize medium</code> | <code>/vsize large</code>"
        )


# ----------------------------------------------------------------------
# Main handler: document (PDF)
# ----------------------------------------------------------------------

@router.message(F.document)
async def on_document(message: Message, bot: Bot):
    user = message.from_user
    if user is None:
        return

    if not config.ADMIN_IDS:
        await message.answer(
            f"⚙️ Config ready nahi: aapka ID = <b>{user.id}</b>\n"
            "config.py me ADMIN_IDS set karke bot dobara chalao."
        )
        return
    if not _is_admin(message):
        log.warning("Unauthorized document from %s (@%s)", user.id, user.username)
        return

    doc = message.document
    name = doc.file_name or ""

    # Video as document? → video pipeline
    if (doc.mime_type or "").startswith("video/"):
        await _process_video(message, bot, doc, name)
        return

    if doc.mime_type != "application/pdf" and not name.lower().endswith(".pdf"):
        await message.answer("❌ Sirf <b>PDF</b> ya <b>Video</b> file bhejiye.")
        return

    size_mb = (doc.file_size or 0) / 1048576
    limit = _size_limit_mb("pdf")
    if size_mb > limit:
        tip = "" if config.USE_LOCAL_API else "\nTip: PDF ko ~18 MB se neeche compress karo, ya config.py me USE_LOCAL_API on karo (2 GB)."
        await message.answer(
            f"❌ File <b>{size_mb:.1f} MB</b> hai — limit {limit:.0f} MB hai "
            "(Telegram standard API bot ko 20 MB tak hi download karne deti hai)."
            f"{tip}"
        )
        return
    if state["busy"]:
        await message.answer("⏳ Ek kaam pehle complete hone do — abhi ek PDF process ho rahi hai.")
        return

    state["busy"] = True
    job_id = uuid.uuid4().hex[:8]
    src = os.path.join(WORKDIR, f"{job_id}_in.pdf")
    out_name = f"MPM_{_sanitize_stem(name)}_wm.pdf"
    out = os.path.join(config.OUTPUT_DIR, out_name)

    status: Message | None = None
    try:
        status = await message.answer(f"⬇️ Downloading ({size_mb:.1f} MB)…")
        await bot.download(doc, destination=src, timeout=300)

        # ---- quick validation: encrypted? kitne pages? ----
        probe = fitz.open(src)
        try:
            if probe.needs_pass:
                await _safe_edit(status, "❌ Yeh PDF <b>password-protected</b> hai. Password hata ke dobara bhejo.")
                return
            pages = len(probe)
        finally:
            probe.close()
        if pages > config.MAX_PAGES:
            await _safe_edit(
                status,
                f"❌ <b>{pages}</b> pages bahut zyada hain (limit {config.MAX_PAGES}). "
                "PDF ko 2 hisson me baant ke bhejo.",
            )
            return

        opacity, width_frac, margin_frac = _mode_cfg()
        mode = state["mode"]
        await _safe_edit(status, f"🖨️ Watermarking <b>{pages}</b> pages — mode: <b>{mode}</b> …")

        loop = asyncio.get_running_loop()

        def progress(done: int, total: int) -> None:
            asyncio.run_coroutine_threadsafe(
                _safe_edit(status, f"🖨️ Watermarking… {done}/{total} pages"), loop
            )

        def work() -> dict:
            prepared = prepare_logo(opacity)
            job = WatermarkJob(
                src=src, dst=out, logo_png=prepared, mode=mode,
                logo_width_frac=width_frac, margin_frac=margin_frac,
                progress_cb=progress,
            )
            return watermark_pdf(job)

        result = await asyncio.to_thread(work)
        qpdf_used = await asyncio.to_thread(_optional_qpdf, out)
        if qpdf_used:
            result["out_mb"] = os.path.getsize(out) / 1048576

        await asyncio.sleep(0.4)  # last progress edit ko land hone do
        await _safe_edit(status, "✅ <b>Done!</b> Watermarked PDF niche hai — WhatsApp share ke liye ready.")

        delta = result["out_mb"] - result["in_mb"]
        arrow = "▲" if delta > 0.05 else ("▼" if delta < -0.05 else "•")
        caption = (
            "📄 <b>Mera Pashu Mitra — Watermarked PDF</b>\n"
            f"Pages: {result['pages']}   Mode: {mode}\n"
            f"Size: {result['in_mb']:.1f} MB → {result['out_mb']:.1f} MB ({arrow} {abs(delta):.2f} MB)\n"
            f"Time: {result['seconds']}s"
            + ("\nBonus: qpdf compression applied ✔" if qpdf_used else "")
        )
        await message.answer_document(FSInputFile(out, filename=out_name), caption=caption)
        log.info(
            "Job ok: %s → %s (%.2f→%.2f MB, %d pages, %.1fs)",
            name, out_name, result["in_mb"], result["out_mb"],
            result["pages"], result["seconds"],
        )

    except FileNotFoundError as e:
        await _safe_edit(status, f"❌ {e}")
    except PermissionError as e:
        await _safe_edit(status, f"❌ {e}")
    except Exception as e:
        log.exception("Job failed")
        await _safe_edit(
            status,
            f"❌ Koi technical galti ho gayi: <code>{e}</code>\n"
            "Console me full error dekh ke dobara try karo.",
        )
    finally:
        state["busy"] = False
        if os.path.exists(src):
            try:
                os.remove(src)
            except OSError:
                pass


# ----------------------------------------------------------------------
# Video pipeline (Shorts)
# ----------------------------------------------------------------------

async def _process_video(message: Message, bot: Bot, file_obj, name: str):
    """Video download karo → right-side logo → Shorts-ready MP4 wapas."""
    if shutil.which("ffmpeg") is None:
        await message.answer("❌ " + INSTALL_HELP)
        return

    size_mb = (file_obj.file_size or 0) / 1048576
    limit = _size_limit_mb("video")
    if size_mb > limit:
        tip = ("" if config.USE_LOCAL_API else
               "\nOptions: (1) 720p me compress karo (README me 1-line command), "
               "(2) config.py me USE_LOCAL_API on karo (2 GB tak).")
        await message.answer(
            f"❌ Video <b>{size_mb:.1f} MB</b> hai — limit {limit:.0f} MB hai "
            "(Telegram standard API 20 MB tak hi download deti hai)."
            f"{tip}"
        )
        return
    if state["busy"]:
        await message.answer("⏳ Ek kaam pehle complete hone do — abhi ek file process ho rahi hai.")
        return

    state["busy"] = True
    job_id = uuid.uuid4().hex[:8]
    src = os.path.join(WORKDIR, f"{job_id}_in.mp4")
    out_name = f"MPM_{_sanitize_stem(name)}.mp4"
    out = os.path.join(config.OUTPUT_DIR, out_name)

    status: Message | None = None
    try:
        status = await message.answer(f"⬇️ Video downloading ({size_mb:.1f} MB)…")
        await bot.download(file_obj, destination=src, timeout=300)

        info = await asyncio.to_thread(probe_video, src)
        if info["width"] == 0:
            await _safe_edit(status, "❌ Video stream nahi mili — file kharab lag rahi hai. Dobara bhejo.")
            return

        landscape = info["width"] > info["height"]
        vpos = state["vpos"]
        total_s = max(1, int(round(info["duration"])))
        note = " + 9:16 Shorts conversion (blurred background)" if landscape else ""
        await _safe_edit(
            status,
            f"🎬 Video watermarking — logo: right-{vpos}{note} … 0/{total_s}s",
        )

        loop = asyncio.get_running_loop()

        def progress(done: int, total: int) -> None:
            asyncio.run_coroutine_threadsafe(
                _safe_edit(status, f"🎬 Video watermarking… {done}/{total}s"), loop
            )

        def work() -> dict:
            prepared = prepare_logo(config.VIDEO_LOGO_OPACITY)
            job = VideoJob(
                src=src, dst=out, logo_png=prepared, position=vpos,
                logo_width_frac=state["vsize"],
                margin_frac=config.VIDEO_LOGO_MARGIN,
                progress_cb=progress,
            )
            return watermark_video(job)

        result = await asyncio.to_thread(work)

        await asyncio.sleep(0.4)  # last progress edit ko land hone do
        await _safe_edit(status, "✅ <b>Done!</b> Watermarked video niche hai — Shorts upload ke liye ready.")

        delta = result["out_mb"] - result["in_mb"]
        arrow = "▲" if delta > 0.05 else ("▼" if delta < -0.05 else "•")
        fmt = f"\nFormat: {result['out_w']}x{result['out_h']}  9:16 Shorts-ready ✔" if result["was_landscape"] else ""
        caption = (
            "🎬 <b>Mera Pashu Mitra — Watermarked Video</b>\n"
            f"Length: {result['duration']}s   Logo: right-{state['vpos']}{fmt}\n"
            f"Size: {result['in_mb']:.1f} MB → {result['out_mb']:.1f} MB ({arrow} {abs(delta):.2f} MB)\n"
            f"Time: {result['seconds']}s"
        )
        await message.answer_video(FSInputFile(out, filename=out_name), caption=caption)
        log.info(
            "Video job ok: %s → %s (%.2f→%.2f MB, %ss, %s, %.1fs)",
            name, out_name, result["in_mb"], result["out_mb"],
            result["duration"], "9:16-converted" if result["was_landscape"] else "portrait",
            result["seconds"],
        )

    except FFmpegMissingError as e:
        await _safe_edit(status, f"❌ {e}")
    except FileNotFoundError as e:
        await _safe_edit(status, f"❌ {e}")
    except Exception as e:
        log.exception("Video job failed")
        await _safe_edit(
            status,
            f"❌ Video processing fail ho gayi: <code>{e}</code>\n"
            "Console me full error dekh ke dobara try karo.",
        )
    finally:
        state["busy"] = False
        if os.path.exists(src):
            try:
                os.remove(src)
            except OSError:
                pass


@router.message(F.video)
async def on_video(message: Message, bot: Bot):
    user = message.from_user
    if user is None:
        return
    if not config.ADMIN_IDS:
        await message.answer(
            f"⚙️ Config ready nahi: aapka ID = <b>{user.id}</b>\n"
            "config.py me ADMIN_IDS set karke bot dobara chalao."
        )
        return
    if not _is_admin(message):
        log.warning("Unauthorized video from %s (@%s)", user.id, user.username)
        return
    v = message.video
    await _process_video(message, bot, v, v.file_name or "")


# ----------------------------------------------------------------------
# Error handler
# ----------------------------------------------------------------------

@router.error()
async def on_error(event: ErrorEvent) -> bool:
    log.exception("Unhandled update error", exc_info=event.exception)
    msg = event.update.message if event.update else None
    if msg is not None:
        try:
            await msg.answer("❌ Koi technical galti ho gayi. Console me error dekh ke dobara try karo.")
        except Exception:
            pass
    return True


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

async def main() -> None:
    if "PASTE" in config.BOT_TOKEN or not config.BOT_TOKEN:
        raise SystemExit("⚠️  Pehle config.py me BOT_TOKEN daalo — @BotFather se /newbot kar ke token lo.")

    if shutil.which("ffmpeg"):
        log.info("ffmpeg mil gaya — video watermarking ready")
    else:
        log.warning("ffmpeg NA mila — video feature band hai. Install: sudo apt install ffmpeg")

    bot_kwargs = {"default": DefaultBotProperties(parse_mode=ParseMode.HTML)}
    if config.USE_LOCAL_API:
        bot_kwargs["base_url"] = config.LOCAL_API_URL
        bot_kwargs["local_mode"] = True
        log.info("Local Bot API mode ON: %s (2 GB files)", config.LOCAL_API_URL)

    bot = Bot(token=config.BOT_TOKEN, **bot_kwargs)
    dp = Dispatcher()
    dp.include_router(router)

    me = await bot.get_me()
    log.info("Bot @%s ready — /start se shuru karo", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped. Bye!")
