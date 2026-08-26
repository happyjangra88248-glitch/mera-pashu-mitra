# =============================================================
#  MERA PASHU MITRA  •  Watermark Bot — Configuration
#  Is file me sirf apni settings badlein. Baaki code haath na lagayen.
# =============================================================

import os

# ------------------------------------------------------------
# 1) BOT TOKEN  (BOT_TOKEN environment variable me set karo)
# ------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# ------------------------------------------------------------
# 2) ADMIN IDS  (ADMIN_IDS me comma-separated Telegram IDs set karo)
# ------------------------------------------------------------
ADMIN_IDS: set[int] = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}

# ------------------------------------------------------------
# 3) LOGO
#    Apna logo (yellow background wala PNG bhi chalega — bot khud
#    background hata kar transparent bana dega) yahan rakho:
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "assets", "logo.png")

# Watermarked PDFs yahan bhi save hongi (backup + seedha share ke liye)
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# ------------------------------------------------------------
# 4) LIMITS  (Telegram standard Bot API: bot ko download max 20 MB)
# ------------------------------------------------------------
MAX_INPUT_MB = 19    # PDF — isse badi file reject hogi (safe margin)
MAX_VIDEO_MB = 19    # VIDEO — isse badi file reject hogi (safe margin)
MAX_PAGES = 500      # RAM safety ke liye page limit

# Badi files (video 20 MB+) ke liye: local Bot API server chalao
# (README me docker command hai) aur neeche wala flag ON karo.
USE_LOCAL_API = False
LOCAL_API_URL = "http://127.0.0.1:8081/bot"

# ------------------------------------------------------------
# 5) WATERMARK LOOK — PDF
# ------------------------------------------------------------
CENTER_OPACITY = 0.25      # center mode: 0.0 = invisible, 1.0 = full (0.20-0.30 recommended)
CORNER_OPACITY = 0.50      # corner mode me logo chhota hota hai, isliye zyada saaf
CENTER_LOGO_WIDTH = 0.30   # page width ka fraction (0.30 = 30%)
CORNER_LOGO_WIDTH = 0.14   # page width ka fraction
CORNER_MARGIN = 0.035      # corner se kitni door (page width ka fraction)
LOGO_MAX_PX_WIDTH = 400    # logo isse chhota karke embed hota hai (file size bachane ke liye)
BG_TOLERANCE = 45          # background-removal tolerance (flat background: 30-60 best)

# ------------------------------------------------------------
# 6) WATERMARK LOOK — VIDEO (Shorts)
#    Logo hamesha RIGHT side par lagta hai; /vpos se position, /vsize se size.
# ------------------------------------------------------------
VIDEO_LOGO_OPACITY = 0.90  # video par logo saaf dikhna chahiye (0.8-1.0 best)
VIDEO_LOGO_WIDTH = 0.16    # video width ka fraction (0.12=chhota, 0.16=medium, 0.20=bada)
VIDEO_LOGO_MARGIN = 0.04   # right/top edge se doori (width ka fraction)
