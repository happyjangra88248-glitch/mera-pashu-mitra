# 🐄🐐 Mera Pashu Mitra — PDF Watermark Bot

**PDF** bhejo → har page par MPM logo, **optimized WhatsApp-share-ready PDF** wapas.
**Video** bhejo → right side par MPM logo, **Shorts-ready video** wapas (landscape auto 9:16 ho jata hai).
Text layer kabhi image me convert nahi hota — notes searchable rehte hain aur file size low rehta hai.

**Stack:** aiogram 3 + PyMuPDF + Pillow + numpy + ffmpeg (video ke liye)

---

## 📁 Folder structure

```
mera-pashu-mitra/
├── bot.py               # Telegram bot (main entry point)
├── config.py            # Runtime settings and environment variables
├── watermark.py         # PDF watermark engine (logo prep + stamping)
├── video_watermark.py   # Video watermark engine (ffmpeg, Shorts-ready)
├── smoke_test.py        # Telegram ke bina test (optional)
├── requirements.txt
├── assets/
│   └── logo.png         # ← APNA LOGO YAHAN RAKHO (yellow bg PNG bhi chalega)
├── output/              # Watermarked PDF/Video yahan save hoti hain
└── tmp/                 # Temporary files (auto cleanup)
```

---

## 🚀 Setup (VS Code me)

1. **Project folder VS Code me kholo** aur terminal banao (`` Ctrl+` ``).

2. **Virtual environment banao:**

   Ubuntu:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   Windows:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Libraries + ffmpeg install karo:**
   ```bash
   pip install -r requirements.txt
   sudo apt install ffmpeg      # Ubuntu/Linux — video feature ke liye
   ```
   Windows me ffmpeg ke liye: `winget install ffmpeg`

4. **Apna logo rakho:** apna logo PNG file ke roop me `assets/logo.png` naam se rakho.
   ✅ Yellow background wala bhi chalega — bot khud background hata kar transparent bana dega.
   ✅ Transparent PNG ho to wo bhi chalega.

5. **Bot token lo:** Telegram me **@BotFather** → `/newbot` → token copy karo.

6. **Environment variables set karo** (`.env.example` dekho):
  - `BOT_TOKEN` — BotFather wala token
  - `ADMIN_IDS` — apna Telegram user ID (dhundhne ke liye Telegram me **@userinfobot** se puchho)

  Windows PowerShell:
  ```powershell
  $env:BOT_TOKEN = "BotFather-token"
  $env:ADMIN_IDS = "123456789"
  ```

7. **Bot chalao:**
   ```bash
   python bot.py
   ```

8. **Telegram me apne bot ko PDF bhejo** — bas. Output `output/` folder me bhi save hoti hai.

---

## 🎛️ Usage

| Kya karna hai | Kaise |
|---|---|
| PDF watermark karo | Bot ko seedha PDF file bhejo |
| Video (Shorts) watermark karo | Bot ko seedha video bhejo — logo RIGHT side par lagta hai |
| Video logo ki position | `/vpos top` (default) · `/vpos mid` · `/vpos bottom` |
| PDF logo beech me halka (default) | `/mode center` |
| PDF logo bottom-right chhota saaf | `/mode corner` |
| Help | `/help` |

Har response me size report aata hai: `2.4 MB → 2.6 MB (▲ 0.2 MB)` — taake aap WhatsApp budget track kar sako.

---

## 🎬 Video (Shorts) — kaise kaam karta hai

- **Logo position**: hamesha **RIGHT side** par. Default `top` (upar-right) — kyunki YouTube Shorts ke
  like/comment/share buttons right-beech me hote hain, isliye upar-right me logo unke peeche nahi chhupta.
  `/vpos mid` ya `/vpos bottom` se badal sakte ho.
- **Landscape video bhejo to kya hoga?**: bot automatically **9:16 (1080×1920)** me convert kar deta hai —
  upar/neeche **blurred background** ke saath (Reels/Shorts ka standard professional look). Content crop nahi hota.
- **Quality**: H.264 CRF 20 (visually original jaisa), audio **copy** (AAC par zero loss),
  `yuv420p` (YouTube 100% compatible), `+faststart` (WhatsApp par instant play).
- **Same logo**: PDF wala hi permanent logo use hota hai — alag video-logo bhejne ki zaroorat nahi.
  Video par thoda zyada saaf (0.90 opacity) lagta hai taake brand pehchaan achi bane.

### ⚠️ 20 MB video limit (Telegram API)

60-second ka 1080p Shorts video aam taur par 15-40 MB hota hai, lekin standard Bot API sirf
20 MB tak download karne deta hai. Do options:

**Option 1 — compress karo (sabse aasaan):**
```bash
ffmpeg -i input.mp4 -vf "scale=720:1280" -c:v libx264 -crf 28 -preset fast \
  -c:a aac -b:a 128k output_720p.mp4
```
720p 60s ≈ 8-15 MB — Shorts ke liye bilkul kaafi quality.

**Option 2 — local Bot API server (2 GB tak):**
```bash
docker run -d --name tg-bot-api --init -p 8081:8081 aiogram/telegram-bot-api
```
Phir `config.py` me `USE_LOCAL_API = True` karo (URL default `http://127.0.0.1:8081/bot` hai).

---

## ⚙️ Tuning (config.py)

| Setting | Kaam |
|---|---|
| `CENTER_OPACITY = 0.25` | PDF center mode me logo kitna saaf (0.10 se 0.35 ke beech best) |
| `CORNER_OPACITY = 0.50` | PDF corner mode me logo ki visibility |
| `CENTER_LOGO_WIDTH = 0.30` | PDF logo ki width, page width ka fraction |
| `CORNER_LOGO_WIDTH = 0.14` | PDF corner logo ki width |
| `VIDEO_LOGO_OPACITY = 0.90` | Video logo ki visibility (0.8-1.0 best) |
| `VIDEO_LOGO_WIDTH = 0.20` | Video logo ki width, video width ka fraction (0.18-0.24 best) |
| `BG_TOLERANCE = 45` | Background removal ki tolerance (dheela background ho to 60 try karo) |

Settings badalne par logo cache **khud refresh** ho jati hai — kuch aur karne ki zaroorat nahi.

---

## ✅ Test (Telegram ke bina)

```bash
python smoke_test.py
```

Yeh fake yellow MPM logo + fake vet-notes PDF banata hai, watermark karta hai,
size report karta hai, aur `output/preview_page1.png` render karta hai
(jisme aap nazar se check kar sakte ho ki text saaf hai ya nahi).

---

## 🧯 Troubleshooting

| Problem | Fix |
|---|---|
| `❌ File X MB — Telegram limit` | PDF ko ~18 MB se neeche compress karo (PDF24, iLovePDF, ya `gs -dPDFSETTINGS=/ebook`) |
| `❌ Video X MB — Telegram limit` | 720p me compress karo (upar wala ffmpeg command), ya `USE_LOCAL_API` on karo |
| `ffmpeg install nahi` wali error | Ubuntu: `sudo apt install ffmpeg` · Windows: `winget install ffmpeg`, phir bot restart |
| `Logo nahi mila` | `assets/logo.png` par file rakhi hai ya nahi — check karo |
| `PDF password-protected` | Password hata ke bhejo (bot encrypted PDF modify nahi kar sakta) |
| Logo ka background bilkul saaf na hat | `config.py` me `BG_TOLERANCE` badhao (45 → 60) |
| `qpdf` warning | Optional hai — `sudo apt install qpdf` se extra compression milta hai |
| `magic` library warning (Ubuntu) | `sudo apt install libmagic1` |

**Extra compression (optional, recommended):**
```bash
sudo apt install qpdf
```
Bot khud detect kar lega, koi config change nahi.

---

## 📌 Design notes (kyun kaam karta hai)

- **Vector-preserving watermark:** logo ek chhota PNG object hai jo har page par overlay hota hai —
  text kabhi rasterize nahi hota. Isliye output size ≈ input size + ~50-100 KB.
- **Background flood-fill:** sirf edges se connected background pixels hatte hain, isliye
  logo ke andar ka yellow/kaala/same color safe rehta hai.
- **Opacity baking:** opacity ko alpha channel me hi bake kiya jaata hai, isliye
  WhatsApp/Google Drive/koisi bhi viewer par same look — kisi viewer par "transparent nahi dikhne" wali problem nahi.
- **Per-page geometry:** mixed portrait/landscape pages bhi sahi watermark hote hain.
- **Video pipeline (ffmpeg):** transparent logo `overlay` filter se har frame par lagta hai.
  Landscape video ke liye `split → blur → crop → center-overlay` chain se 9:16 (1080×1920)
  Shorts format banta hai — content kabhi crop nahi hota, audio lossless copy hota hai.
- **RAM/CPU safety:** sab processing worker thread me, 500 page / 19 MB cap, single-job lock
  (ek saath do heavy files process nahi hoti).
- **Admin-only:** sirf `ADMIN_IDS` wale use kar sakte hain.
