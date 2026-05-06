# Tekion DMS Uploader

[![Release](https://img.shields.io/github/v/release/praveenagarwal24/tekion-dms-uploader?label=latest&color=4f8ef7)](https://github.com/praveenagarwal24/tekion-dms-uploader/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Mac-lightgrey)](https://github.com/praveenagarwal24/tekion-dms-uploader)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Automates bulk VIN media uploads to Tekion Cloud DMS.**  
Built by [Spyne](https://spyne.ai) — drop your VIN folder, hit Start, and walk away.

🌐 **[View docs site →](https://praveenagarwal24.github.io/tekion-dms-uploader/)**

---

## Quick Start

### Windows
1. [**Download the latest release**](https://github.com/praveenagarwal24/tekion-dms-uploader/releases/latest/download/tekion-dms-uploader.zip)
2. Unzip anywhere
3. Double-click `start_windows.bat`
4. Browser opens at `http://localhost:7432` — paste your folder path and click **Start**

### Mac / Linux
```bash
# Download & unzip, then:
chmod +x start_mac.sh
./start_mac.sh
```

> **Requires Python 3.8+** — [download here](https://python.org) if needed.  
> First run downloads Playwright Chromium (~150 MB, one time only).

---

## What it does

Automates this workflow for every VIN in your folder:

| Step | Action | Type |
|------|--------|------|
| 1 | Scan folder, extract .zip files, delete originals | Auto |
| 2 | Open Tekion DMS, fill credentials | Auto |
| 3 | Enter OTP | **Manual** |
| 4 | Navigate to Vehicle Inventory | Auto |
| 5 | Search VIN → open record → Media tab → select all → delete | Auto |
| 6 | Upload images from local VIN folder | Auto |
| 7 | Click Save, dismiss popups, repeat until search page returns | Auto |

---

## Configuration

Edit `config.json` to change credentials or settings — no Python knowledge needed:

```json
{
  "dms_url": "https://app.tekioncloud.com/",
  "username": "your@email.com",
  "password": "yourpassword",
  "port": 7432,
  "image_extensions": [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"],
  "save_retry_attempts": 8
}
```

---

## Folder structure

```
/your/vins/folder/
├── VIN1234567.zip       ← extracted to VIN1234567/ automatically
├── VIN8901234.zip
└── ...

After extraction:
├── VIN1234567/
│   ├── front.jpg
│   ├── rear.jpg
│   └── ...
└── VIN8901234/
    └── ...
```

Plain (already-unzipped) VIN folders work too.

---

## Architecture

```
Browser (localhost:7432)
    ↕  HTTP polling
server.py  (Python, runs locally)
    ↕  Playwright
Chromium  (real visible browser)
    ↕  HTTPS
app.tekioncloud.com
```

Everything runs on your machine. No data leaves your computer except what the browser sends to Tekion.

---

## Files

```
tekion-dms-uploader/
├── server.py              Python backend + Playwright automation
├── config.json            Editable credentials & settings
├── requirements.txt       pip dependencies
├── start_windows.bat      Windows launcher
├── start_mac.sh           Mac/Linux launcher
├── ui/
│   └── index.html         Browser control UI
├── docs/
│   └── index.html         GitHub Pages docs site
└── .github/
    └── workflows/
        ├── release.yml    Auto-builds zip on every push to main
        └── docs.yml       Auto-deploys docs site
```

---

## Development

```bash
git clone https://github.com/praveenagarwal24/tekion-dms-uploader
cd tekion-dms-uploader
pip install -r requirements.txt
python -m playwright install chromium
python server.py
```

Every push to `main` automatically:
1. Packages a fresh `tekion-dms-uploader.zip`
2. Creates/updates the `latest` GitHub Release
3. Deploys the docs site to GitHub Pages

---

## License

MIT — free to use, modify, and distribute.
