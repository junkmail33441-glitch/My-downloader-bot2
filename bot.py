"""
Telegram Media Downloader Bot
Supports: YouTube, Instagram, TikTok, Twitter/X, Pinterest, Facebook, Reddit
"""

import os
import re
import asyncio
import tempfile
import logging
import subprocess
import requests as req
from pathlib import Path
from urllib.parse import urlparse

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import yt_dlp

# ── Config ─────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
MAX_FILE_MB = 50

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


def kill_other_instances():
    """Call deleteWebhook and close any existing polling sessions."""
    try:
        req.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
            params={"drop_pending_updates": True},
            timeout=10,
        )
        req.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/close",
            timeout=10,
        )
        log.info("Cleared existing bot sessions.")
    except Exception as e:
        log.warning(f"Could not clear sessions: {e}")
    import time; time.sleep(3)


# ── URL pattern matching ────────────────────────────────────────────────────────
URL_REGEX = re.compile(
    r"https?://"
    r"(?:www\.)?"
    r"(?:"
    r"youtu\.be/[A-Za-z0-9_\-]+"
    r"|(?:youtube\.com|youtube-nocookie\.com)/(?:watch\?v=|shorts/|embed/)[A-Za-z0-9_\-]+"
    r"|instagram\.com/(?:p|reel|tv)/[A-Za-z0-9_\-]+"
    r"|tiktok\.com/@[^/]+/video/\d+"
    r"|vm\.tiktok\.com/[A-Za-z0-9]+"
    r"|twitter\.com/\w+/status/\d+"
    r"|x\.com/\w+/status/\d+"
    r"|pinterest\.com/pin/\d+"
    r"|pin\.it/[A-Za-z0-9]+"
    r"|reddit\.com/r/[^/]+/comments/[A-Za-z0-9]+"
    r"|redd\.it/[A-Za-z0-9]+"
    r"|facebook\.com/(?:watch/?\?v=\d+|reel/\d+|[^/]+/videos/\d+)"
    r"|fb\.watch/[A-Za-z0-9]+"
    r")"
    r"[^\s]*",
    re.IGNORECASE,
)


def extract_url(text: str) -> str | None:
    m = URL_REGEX.search(text)
    return m.group(0) if m else None


def platform_name(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    mapping = {
        "youtu.be": "YouTube", "youtube.com": "YouTube",
        "instagram.com": "Instagram",
        "tiktok.com": "TikTok", "vm.tiktok.com": "TikTok",
        "twitter.com": "Twitter/X", "x.com": "Twitter/X",
        "pinterest.com": "Pinterest", "pin.it": "Pinterest",
        "reddit.com": "Reddit", "redd.it": "Reddit",
        "facebook.com": "Facebook", "fb.watch": "Facebook",
    }
    return mapping.get(host, host)


def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def build_ydl_opts(tmpdir: str, audio_only: bool = False) -> dict:
    outtmpl = str(Path(tmpdir) / "%(title).60s.%(ext)s")
    has_ffmpeg = ffmpeg_available()

    if audio_only:
        if has_ffmpeg:
            return {
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "quiet": True,
                "no_warnings": True,
            }
        else:
            return {
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
                "quiet": True,
                "no_warnings": True,
            }

    if has_ffmpeg:
        fmt = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]/best"
    else:
        fmt = "best[height<=720][ext=mp4]/best[height<=720]/best[ext=mp4]/best"

    opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "abort_on_unavailable_fragment": False,
    }
    if has_ffmpeg:
        opts["merge_output_format"] = "mp4"
    return opts


def _do_download(url: str, audio_only: bool) -> tuple[str | None, str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        opts = build_ydl_opts(tmpdir, audio_only)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info is None:
                    return None, "Could not extract info from URL."
                if "entries" in info:
                    entries = [e for e in info["entries"] if e]
                    if not entries:
                        return None, "No downloadable entries found."
                    info = entries[0]
                filename = ydl.prepare_filename(info)
                if not Path(filename).exists():
                    candidates = list(Path(tmpdir).iterdir())
                    if not candidates:
                        return None, "Download produced no output file."
                    filename = str(candidates[0])
                size_mb = Path(filename).stat().st_size / (1024 * 1024)
                if size_mb > MAX_FILE_MB:
                    return None, (
                        f"File is {size_mb:.1f} MB — exceeds Telegram's {MAX_FILE_MB} MB limit.\n"
                        "Try /audio <url> for audio only."
                    )
                dest = Path(tempfile.mktemp(suffix=Path(filename).suffix))
                dest.write_bytes(Path(filename).read_bytes())
                return str(dest), ""
        except yt_dlp.utils.DownloadError as e:
            return None, f"Download failed: {e}"
        except Exception as e:
            return None, f"Unexpected error: {e}"


async def download_media(url: str, audio_only: bool = False) -> tuple[str | None, str]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _do_download, url, audio_only)


# ── Handlers ───────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send any supported URL to download.\n\n"
        "Supported: YouTube · Instagram · TikTok · Twitter/X · Pinterest · Reddit · Facebook\n\n"
        "Commands:\n"
        "/dl <url>    — download video\n"
        "/audio <url> — download audio (MP3)\n"
        "/help        — this message"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await cmd_start(update, ctx)


async def handle_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE, url: str, audio_only: bool = False):
    platform = platform_name(url)
    status_msg = await update.message.reply_text(f"⏳ Downloading from {platform}…")

    filepath, error = await download_media(url, audio_only)

    if error:
        await status_msg.edit_text(f"❌ {error}")
        return

    try:
        ext = Path(filepath).suffix.lower()
        with open(filepath, "rb") as f:
            if audio_only or ext in (".mp3", ".m4a", ".ogg", ".opus", ".flac", ".wav"):
                await update.message.reply_audio(audio=f)
            elif ext in (".mp4", ".mov", ".webm", ".mkv"):
                await update.message.reply_video(video=f)
            else:
                await update.message.reply_document(document=f)
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to send file: {e}")
    finally:
        try:
            os.unlink(filepath)
        except Exception:
            pass


async def cmd_dl(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = " ".join(ctx.args or [])
    url = extract_url(args)
    if not url:
        await update.message.reply_text("Usage: /dl <url>")
        return
    await handle_url(update, ctx, url, audio_only=False)


async def cmd_audio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = " ".join(ctx.args or [])
    url = extract_url(args)
    if not url:
        await update.message.reply_text("Usage: /audio <url>")
        return
    await handle_url(update, ctx, url, audio_only=True)


async def message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    url = extract_url(text)
    if url:
        await handle_url(update, ctx, url, audio_only=False)


# ── Entry point ─────────────────────────────────────────────────────────────────
def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN env var or replace the placeholder in bot.py")

    kill_other_instances()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("dl", cmd_dl))
    app.add_handler(CommandHandler("audio", cmd_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    log.info("Bot running…")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
