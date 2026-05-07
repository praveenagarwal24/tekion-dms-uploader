# DMS Upload Automation — Setup Guide
### Tekion Cloud · Spyne | Windows Setup

---

## What this does
Automatically uploads vehicle images to Tekion DMS for multiple VINs.
You provide a folder of zipped VINs → it logs in, deletes old images, uploads new ones, saves. All automated except OTP.

---

## One-time Setup (do this once)

### Step 1 — Install Python
1. Open browser → go to **https://python.org/downloads**
2. Click **Download Python 3.x.x** (big yellow button)
3. Run the installer
4. ⚠️ **IMPORTANT** — check **"Add Python to PATH"** before clicking Install
5. Click **Install Now** → wait for it to finish

### Step 2 — Download the tool
1. Go to **https://github.com/praveenagarwal24/tekion-dms-uploader/releases/latest**
2. Click **tekion-dms-uploader.zip** to download
3. Right-click the zip → **Extract All** → choose a location (e.g. Desktop)
4. You should now have a folder called **tekion-dms-uploader**

### Step 3 — First run (installs browser automatically)
1. Open the **tekion-dms-uploader** folder
2. Double-click **start_windows.bat**
3. A black window opens — it will install Playwright and download Chrome (~150 MB)
4. This takes 2–5 minutes on first run only
5. When done, your browser opens at **http://localhost:7432**

---

## Every Day Usage

### Step 1 — Prepare your VIN folder
Create a folder anywhere (e.g. `C:\Users\YourName\Desktop\VINs`)
Put all your zipped VINs inside it:
```
VINs\
  1C4RJKBG5R8547838.zip
  1C4HJXFN2MW633565.zip
  2GNAXHEV7J6176689.zip
  ...
```
✅ Plain unzipped VIN folders also work fine

### Step 2 — Start the tool
Double-click **start_windows.bat** inside the tekion-dms-uploader folder
→ Browser opens at http://localhost:7432

### Step 3 — Enter folder path
In the UI, paste your VIN folder path into the text box:
```
C:\Users\YourName\Desktop\VINs
```
💡 Tip: In Windows Explorer, click the address bar at the top to copy the path

### Step 4 — Click Start automation
The tool will:
- ✅ Unzip all VIN folders automatically
- ✅ Open Tekion DMS in Chrome
- ✅ Fill in login credentials
- ⏸️ PAUSE for OTP — you enter it manually
- ✅ Navigate to Vehicle Inventory
- ✅ For each VIN: search → open → delete old images → upload new → save
- ✅ Move to next VIN automatically

### Step 5 — Enter OTP
When the orange banner appears in the UI:
1. Switch to the Chrome window that opened
2. Enter the OTP
3. Come back to the UI tab
4. Click **"OTP entered — continue"**

### Step 6 — Watch it run
- Green = done ✅
- Blue = currently processing
- Red = failed ❌ (will show in log)
- You can use your computer normally while it runs
- Do NOT close the black Terminal window or the Chrome automation window

---

## Updating to latest version

When there's a new update, just run this in the black window (Command Prompt):
```
cd C:\Users\YourName\Desktop\tekion-dms-uploader
curl -O https://raw.githubusercontent.com/praveenagarwal24/tekion-dms-uploader/main/server.py
start_windows.bat
```

Or simply re-download the zip from:
**https://github.com/praveenagarwal24/tekion-dms-uploader/releases/latest**

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Black window closes immediately | Python not installed or not added to PATH — reinstall Python, check "Add to PATH" |
| "playwright not found" error | Run `pip install playwright` then `python -m playwright install chromium` in Command Prompt |
| Browser doesn't open | Manually go to http://localhost:7432 in your browser |
| VIN not found in search | Check VIN folder name matches exactly what's in Tekion |
| Images not uploading | Check image files are .jpg/.jpeg/.png (not .heic or other formats) |
| Tool stops mid-way | Click Reset, fix the issue, start again — completed VINs won't be re-done |

---

## Folder structure expected

```
Your VIN folder\
  ├── VIN1234567890.zip     ← gets extracted automatically
  ├── VIN0987654321.zip
  └── VINABCDEF12345\       ← plain folders work too
      ├── front.jpg
      ├── rear.jpg
      └── ...
```

---

## Credentials (pre-configured)
- URL: https://app.tekioncloud.com/
- Username: catalogue@spyne.ai
- Password: Spyne@123
- OTP: entered manually each session

To change credentials, edit **config.json** in the tool folder with Notepad.

---

## Need help?
Contact: praveen@spyne.ai
Repo: https://github.com/praveenagarwal24/tekion-dms-uploader
