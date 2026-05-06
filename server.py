"""
DMS Upload Automation Server
Cross-platform (Windows + Mac)
Run: python server.py
"""

import os
import sys
import json
import time
import zipfile
import threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import webbrowser

# ── Load config ───────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json"
try:
    with open(CONFIG_PATH) as f:
        CFG = json.load(f)
except FileNotFoundError:
    CFG = {}

DMS_URL      = CFG.get("dms_url",   "https://app.tekioncloud.com/")
DMS_USER     = CFG.get("username",  "")
DMS_PASS     = CFG.get("password",  "")
PORT         = CFG.get("port",      7432)
IMG_EXTS     = set(CFG.get("image_extensions", [".jpg",".jpeg",".png",".webp",".gif",".bmp"]))
SAVE_RETRIES = CFG.get("save_retry_attempts", 8)

# ── State ─────────────────────────────────────────────────────────────────────
state = {
    "status": "idle",
    "step": 0,
    "log": [],
    "vins": [],
    "current_vin": None,
    "done_vins": [],
    "failed_vins": [],
    "total": 0,
}
stop_flag         = threading.Event()
otp_event         = threading.Event()
automation_thread = None

# ── Logging ───────────────────────────────────────────────────────────────────
def log(kind, msg):
    entry = {"t": time.strftime("%H:%M:%S"), "kind": kind, "msg": msg}
    state["log"].append(entry)
    print(f"[{entry['t']}] [{kind.upper():5}] {msg}")

def set_step(n):
    state["step"] = n

# ── File helpers ──────────────────────────────────────────────────────────────
def unzip_vins(folder: Path):
    zips = list(folder.glob("*.zip"))
    if not zips:
        log("info", "No .zip files found — using existing VIN folders directly")
        return
    log("info", f"Found {len(zips)} zip(s) — extracting...")
    for z in zips:
        if stop_flag.is_set():
            return
        try:
            with zipfile.ZipFile(z, "r") as zf:
                zf.extractall(folder / z.stem)
            z.unlink()
            log("ok", f"Extracted & deleted: {z.name}")
        except Exception as e:
            log("error", f"Failed to extract {z.name}: {e}")

def get_vin_folders(folder: Path):
    vins = []
    for item in sorted(folder.iterdir()):
        if item.is_dir():
            imgs = [f for f in item.iterdir() if f.suffix.lower() in IMG_EXTS]
            if imgs:
                vins.append(item.name)
    return vins

# ── Playwright automation ─────────────────────────────────────────────────────
def run_automation(folder_str: str):
    folder = Path(folder_str)
    stop_flag.clear()
    otp_event.clear()
    state.update({"status":"running","log":[],"done_vins":[],"failed_vins":[],
                  "current_vin":None,"vins":[],"total":0,"step":0})

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("error", "Playwright not installed. Run: pip install playwright && playwright install chromium")
        state["status"] = "error"
        return

    # Step 1 — Unzip
    set_step(1)
    log("info", f"Scanning folder: {folder}")
    unzip_vins(folder)
    if stop_flag.is_set():
        state["status"] = "stopped"; return

    vins = get_vin_folders(folder)
    if not vins:
        log("error", "No VIN folders with images found after extraction")
        state["status"] = "error"; return

    state["vins"]  = vins
    state["total"] = len(vins)
    log("ok", f"Loaded {len(vins)} VIN(s): {', '.join(vins)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        ctx     = browser.new_context(no_viewport=True)
        page    = ctx.new_page()

        # Step 2 — Login
        set_step(2)
        log("info", f"Opening: {DMS_URL}")
        page.goto(DMS_URL)
        page.wait_for_load_state("networkidle", timeout=30000)
        try:
            page.fill(
                'input[type="email"],input[name="email"],'
                'input[placeholder*="email" i],input[placeholder*="user" i]',
                DMS_USER, timeout=10000
            )
            page.fill('input[type="password"]', DMS_PASS, timeout=5000)
            page.click(
                'button[type="submit"],button:has-text("Login"),button:has-text("Sign in")',
                timeout=5000
            )
            log("ok", "Credentials submitted")
        except Exception as e:
            log("warn", f"Auto-fill issue ({e}) — fill manually if needed")

        # Step 3 — OTP (manual)
        set_step(3)
        state["status"] = "otp_wait"
        log("warn", "PAUSED — Enter OTP in browser then click 'OTP entered' in the UI")
        otp_event.wait()
        if stop_flag.is_set():
            browser.close(); state["status"] = "stopped"; return
        state["status"] = "running"
        log("ok", "OTP confirmed — waiting for dashboard...")
        page.wait_for_load_state("networkidle", timeout=60000)
        time.sleep(2)

        # Step 4 — Navigate to Vehicle Inventory
        set_step(4)
        log("info", "Navigating to Vehicle Inventory...")
        try:
            page.click(
                '[data-testid*="app"],[class*="app-menu"],[class*="grid-menu"],'
                '[aria-label*="apps" i],[class*="launcher"],[class*="nine-dot"]',
                timeout=8000
            )
            time.sleep(1)
            page.click('text=Vehicle Inventory', timeout=8000)
            log("ok", "Opened Vehicle Inventory")
        except Exception as e:
            log("warn", "Auto-nav failed — please navigate manually, then click Resume")
            state["status"] = "otp_wait"
            otp_event.clear()
            otp_event.wait()
            state["status"] = "running"
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)

        # Steps 5-7 — Per-VIN loop
        for vin in vins:
            if stop_flag.is_set():
                break
            state["current_vin"] = vin
            log("info", f"━━━ Processing VIN: {vin} ━━━")

            vin_folder = folder / vin
            images = sorted([f for f in vin_folder.iterdir() if f.suffix.lower() in IMG_EXTS])
            if not images:
                log("warn", f"No images in {vin} — skipping")
                state["failed_vins"].append(vin)
                continue

            try:
                # Search
                set_step(5)
                log("info", f"Searching VIN: {vin}")
                try:
                    page.click(
                        'button[class*="search"]:not([class*="result"]),'
                        '[data-testid*="search-icon"],[aria-label="Search"]',
                        timeout=6000
                    )
                    time.sleep(0.4)
                except:
                    pass

                page.keyboard.type(vin)
                page.keyboard.press("Enter")
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(1)

                page.click(f'text={vin}', timeout=10000)
                page.wait_for_load_state("networkidle", timeout=20000)
                time.sleep(2)

                # Media tab
                page.click('text=Media', timeout=10000)
                page.wait_for_load_state("networkidle", timeout=15000)
                time.sleep(1.5)

                # Select all existing images & delete
                log("info", "Checking existing media...")
                checkboxes = page.locator(
                    '[class*="media"] input[type="checkbox"],'
                    '[class*="image-item"] input[type="checkbox"],'
                    'input[type="checkbox"][class*="select"]'
                ).all()

                if checkboxes:
                    log("info", f"Selecting {len(checkboxes)} existing image(s) for deletion")
                    for cb in checkboxes:
                        try: cb.click(timeout=1500)
                        except: pass
                    time.sleep(0.5)
                    page.click(
                        'button[aria-label*="delete" i],button:has-text("Delete"),'
                        '[class*="delete-btn"],[data-testid*="delete"]',
                        timeout=8000
                    )
                    time.sleep(0.5)
                    page.click(
                        '[class*="modal"] button:has-text("Delete"),'
                        '[class*="dialog"] button:has-text("Delete"),'
                        'button[class*="primary"]:has-text("Delete")',
                        timeout=8000
                    )
                    page.wait_for_load_state("networkidle", timeout=20000)
                    log("ok", f"Deleted {len(checkboxes)} image(s)")
                else:
                    log("info", "No existing images to delete")

                # Upload
                set_step(6)
                log("info", f"Uploading {len(images)} image(s)...")
                page.click(
                    'button:has-text("Upload Media"),button:has-text("Upload media"),'
                    '[aria-label*="upload" i],[data-testid*="upload"]',
                    timeout=10000
                )
                time.sleep(1)

                with page.expect_file_chooser(timeout=10000) as fc_info:
                    try:
                        page.click('input[type="file"]', timeout=3000)
                    except:
                        page.click(
                            'button:has-text("Choose"),button:has-text("Browse"),label[for]',
                            timeout=5000
                        )
                fc_info.value.set_files([str(img) for img in images])
                log("ok", f"Files selected — waiting for upload to complete...")
                page.wait_for_load_state("networkidle", timeout=90000)
                time.sleep(3)

                # Save loop
                set_step(7)
                log("info", "Starting save loop...")
                for attempt in range(SAVE_RETRIES):
                    if stop_flag.is_set():
                        break
                    try:
                        for ok_text in ["Okay", "OK", "Ok"]:
                            try:
                                btn = page.locator(f'button:has-text("{ok_text}")').first
                                if btn.is_visible(timeout=1500):
                                    btn.click()
                                    log("info", "Dismissed upload popup")
                                    time.sleep(2)
                            except:
                                pass

                        save_btn = page.locator(
                            'button:has-text("Save"),button[class*="save"]'
                        ).first
                        if not save_btn.is_visible(timeout=1500):
                            log("ok", "Page returned to search — save complete")
                            break
                        save_btn.click()
                        log("info", f"Save clicked (attempt {attempt+1})")
                        time.sleep(2)
                        page.wait_for_load_state("networkidle", timeout=20000)
                    except:
                        log("ok", "Save loop done")
                        break

                state["done_vins"].append(vin)
                log("ok", f"✓ VIN {vin} completed successfully")

            except Exception as e:
                log("error", f"✗ VIN {vin} failed: {e}")
                state["failed_vins"].append(vin)

            finally:
                state["current_vin"] = None
                time.sleep(1)

        browser.close()

    d, f2 = len(state["done_vins"]), len(state["failed_vins"])
    log("ok", f"━━━ Finished — {d} succeeded, {f2} failed ━━━")
    state["status"] = "done"
    state["step"]   = 8


# ── HTTP Server ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ct):
        try:
            body = Path(path).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._file(Path(__file__).parent / "ui" / "index.html", "text/html")
        elif path == "/state":
            self._json(state)
        elif path == "/stop":
            stop_flag.set(); otp_event.set()
            state["status"] = "stopped"
            self._json({"ok": True})
        elif path == "/otp_done":
            otp_event.set()
            self._json({"ok": True})
        elif path == "/reset":
            state.update({"status":"idle","step":0,"log":[],"vins":[],"current_vin":None,
                          "done_vins":[],"failed_vins":[],"total":0})
            stop_flag.clear(); otp_event.clear()
            self._json({"ok": True})
        elif path == "/config":
            try:
                self._json(json.loads(CONFIG_PATH.read_text()))
            except:
                self._json({})
        else:
            self.send_error(404)

    def do_POST(self):
        path   = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length)) if length else {}

        if path == "/start":
            folder = body.get("folder", "").strip()
            if not folder or not Path(folder).is_dir():
                self._json({"ok": False, "error": f"Folder not found: {folder}"}, 400)
                return
            global automation_thread
            if automation_thread and automation_thread.is_alive():
                self._json({"ok": False, "error": "Already running"})
                return
            stop_flag.clear(); otp_event.clear()
            automation_thread = threading.Thread(
                target=run_automation, args=(folder,), daemon=True
            )
            automation_thread.start()
            self._json({"ok": True})
        else:
            self.send_error(404)


if __name__ == "__main__":
    print(f"\n  ┌─────────────────────────────────────┐")
    print(f"  │  DMS Upload Automation — Spyne      │")
    print(f"  │  http://localhost:{PORT}              │")
    print(f"  └─────────────────────────────────────┘\n")
    server = HTTPServer(("localhost", PORT), Handler)
    threading.Thread(target=open_browser, args=(PORT,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")

def open_browser(port):
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{port}")
