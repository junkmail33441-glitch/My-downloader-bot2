# Telegram Media Downloader Bot

## Supported platforms
YouTube · Instagram · TikTok · Twitter/X · Pinterest · Reddit · Facebook

## Setup

### 1. Get a bot token
Talk to @BotFather on Telegram → /newbot → copy the token.

### 2. Install dependencies
```
pip install -r requirements.txt
```
ffmpeg must also be installed and on PATH (needed for merging video+audio streams and MP3 extraction):
- Ubuntu/Debian: `sudo apt install ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: download from https://ffmpeg.org/download.html and add to PATH

### 3. Run
```bash
export TELEGRAM_BOT_TOKEN="your_token_here"
python bot.py
```
Or inline:
```bash
TELEGRAM_BOT_TOKEN="your_token_here" python bot.py
```

## Commands
| Command | Action |
|---|---|
| `/dl <url>` | Download video (≤720p, ≤50 MB) |
| `/audio <url>` | Download audio as MP3 |
| `/help` | Show help |

Sending a URL directly (without a command) also triggers a video download.

## Notes

### Instagram / TikTok private content
yt-dlp may require cookies for private or login-gated content.
Export your browser cookies to a Netscape-format file and set `cookiefile` in `build_ydl_opts()`:
```python
"cookiefile": "/path/to/cookies.txt",
```
Tools: [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) (Chrome) or equivalent.

### File size limit
Telegram bots are capped at 50 MB per file. Videos exceeding this are rejected with an error suggesting the `/audio` fallback.

### Running persistently
Use systemd, screen, tmux, or deploy to a VPS/cloud instance.

Example systemd unit (`/etc/systemd/system/mediabot.service`):
```ini
[Unit]
Description=Telegram Media Downloader Bot
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/mediabot/bot.py
Environment=TELEGRAM_BOT_TOKEN=your_token_here
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```
sudo systemctl enable --now mediabot
```

### Keeping yt-dlp updated
Sites break yt-dlp extractors regularly. Keep it current:
```
pip install -U yt-dlp
```
