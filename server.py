import os, sys, json, time, zipfile, threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import webbrowser

CONFIG_PATH = Path(__file__).parent / "config.json"
try:
    CFG = json.loads(CONFIG_PATH.read_text())
except:
    CFG = {}

DMS_URL      = CFG.get("dms_url",   "https://app.tekioncloud.com/")
DMS_USER     = CFG.get("username",  "")
DMS_PASS     = CFG.get("password",  "")
PORT         = CFG.get("port",      7432)
IMG_EXTS     = set(CFG.get("image_extensions", [".jpg",".jpeg",".png",".webp",".gif",".bmp"]))
SAVE_RETRIES = CFG.get("save_retry_attempts", 8)

state = {
    "status": "idle", "step": 0, "log": [],
    "vins": [], "current_vin": None,
    "done_vins": [], "failed_vins": [], "total": 0,
}
stop_flag         = threading.Event()
otp_event         = threading.Event()
automation_thread = None

def log(kind, msg):
    entry = {"t": time.strftime("%H:%M:%S"), "kind": kind, "msg": msg}
    state["log"].append(entry)
    print(f"[{entry['t']}] [{kind.upper():5}] {msg}")

def set_step(n):
    state["step"] = n

def safe_wait(page, timeout=10000):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except:
        pass
    time.sleep(2)

def unzip_vins(folder: Path):
    zips = list(folder.glob("*.zip"))
    if not zips:
        log("info", "No .zip files — using existing VIN folders")
        return
    log("info", f"Found {len(zips)} zip(s) — extracting...")
    for z in zips:
        if stop_flag.is_set(): return
        try:
            with zipfile.ZipFile(z, "r") as zf:
                zf.extractall(folder / z.stem)
            z.unlink()
            log("ok", f"Extracted & deleted: {z.name}")
        except Exception as e:
            log("error", f"Failed {z.name}: {e}")

def get_vin_folders(folder: Path):
    vins = []
    for item in sorted(folder.iterdir()):
        if not item.is_dir() or item.name.startswith("__"):
            continue
        imgs = [f for f in item.iterdir() if f.suffix.lower() in IMG_EXTS]
        if imgs:
            vins.append(item.name)
            continue
        for sub in item.iterdir():
            if sub.is_dir() and not sub.name.startswith("__"):
                sub_imgs = [f for f in sub.iterdir() if f.suffix.lower() in IMG_EXTS]
                if sub_imgs:
                    for img in sub_imgs:
                        img.rename(item / img.name)
                    try: sub.rmdir()
                    except: pass
                    vins.append(item.name)
                    break
    return vins

def get_file_count(page):
    """Read 'Showing X Files' text from Media tab."""
    try:
        txt = page.locator('text=/Showing [0-9]+ Files?/i').first.inner_text(timeout=3000)
        return int(''.join(filter(str.isdigit, txt)))
    except:
        return 0

def delete_all_media(page):
    """
    Tekion delete flow (confirmed from screenshots):
    1. Each image has a checkbox visible on hover (bottom-right corner)
    2. Top-right 'Delete' button (with trash icon) deletes selected
    3. Popup: 'Delete Media' → blue 'Delete' button
    Strategy: delete in batches of 50 until count = 0
    """
    # Check total file count
    total = get_file_count(page)
    if total == 0:
        log("info", "No existing media to delete")
        return

    log("info", f"Need to delete {total} existing file(s)...")

    batch = 0
    while True:
        batch += 1
        remaining = get_file_count(page)
        if remaining == 0:
            log("ok", "All media deleted")
            break
        if batch > 20:
            log("warn", "Delete loop safety limit reached")
            break

        log("info", f"Delete batch {batch} — {remaining} file(s) remaining")
        time.sleep(1)

        # Scroll to top so images are visible
        page.keyboard.press("Home")
        time.sleep(0.5)

        # Hover over each image to reveal checkbox, then click it
        # Images are in a grid — find all image containers
        # From screenshot: images are in rows under "Normal Pictures and Videos"
        # Each image has a checkbox that appears on hover
        
        # Try JavaScript approach to click all checkboxes at once (most reliable)
        checked = page.evaluate("""
            () => {
                // Find all image containers and click their checkboxes
                let count = 0;
                
                // Try hovering each image to reveal checkbox
                const imgs = document.querySelectorAll(
                    'img[class*="media"], img[class*="image"], ' +
                    '[class*="media-item"] img, [class*="mediaItem"] img, ' +
                    '[class*="image-container"] img, [class*="imageContainer"] img, ' +
                    '[class*="thumbnail"] img, [class*="Thumbnail"] img, ' +
                    '[class*="media-card"] img, [class*="mediaCard"] img'
                );
                
                // Also try getting parent containers
                const containers = document.querySelectorAll(
                    '[class*="media-item"], [class*="mediaItem"], ' +
                    '[class*="image-item"], [class*="imageItem"], ' +
                    '[class*="media-card"], [class*="mediaCard"], ' +
                    '[class*="thumbnail-wrap"], [class*="thumbnailWrap"]'
                );
                
                // Click checkboxes that are already visible
                const cbs = document.querySelectorAll('input[type="checkbox"]');
                cbs.forEach(cb => { 
                    if (!cb.checked) { cb.click(); count++; }
                });
                
                return { imgs: imgs.length, containers: containers.length, cbs: count };
            }
        """)
        log("info", f"JS found: {checked}")
        time.sleep(0.5)

        # Now hover each image element to trigger checkbox visibility,
        # then click the checkbox via Playwright
        img_elements = page.locator(
            'img[class*="media"], img[class*="image"], '
            '[class*="media-grid"] img, [class*="mediaGrid"] img, '
            '[class*="normal-picture"] img, [class*="normalPicture"] img, '
            '[class*="vehicle-image"] img, [class*="vehicleImage"] img'
        ).all()

        if img_elements:
            log("info", f"Hovering {min(len(img_elements), 50)} images...")
            for img in img_elements[:50]:  # batch of 50
                try:
                    img.hover(timeout=1000)
                    time.sleep(0.15)
                    # Look for checkbox near this image
                    parent = img.locator('xpath=..').first
                    cb = parent.locator('input[type="checkbox"]').first
                    if cb.is_visible(timeout=500):
                        if not cb.is_checked():
                            cb.click(timeout=500)
                except:
                    continue

        time.sleep(0.5)

        # Check if any checkboxes are now checked
        checked_count = page.evaluate(
            "() => document.querySelectorAll('input[type=\"checkbox\"]:checked').length"
        )
        log("info", f"Checkboxes selected: {checked_count}")

        if checked_count == 0:
            # Last resort: just click the Delete button directly
            # (some Tekion versions allow deleting all without selecting)
            log("warn", "No checkboxes selected — trying direct Delete button")

        # Click the Delete button (top right, has trash icon)
        # From screenshot: button text is "Delete" with trash icon, far right
        delete_clicked = False
        for sel in [
            'button:has-text("Delete")',
            '[class*="delete-button"]',
            '[aria-label*="delete" i]',
            'button[class*="delete"]',
            'button[class*="danger"]',
        ]:
            try:
                btns = page.locator(sel).all()
                # Click the rightmost/last Delete button (top-right of media section)
                for btn in reversed(btns):
                    if btn.is_visible(timeout=1000):
                        btn.click()
                        delete_clicked = True
                        log("info", "Clicked Delete button")
                        break
                if delete_clicked:
                    break
            except:
                continue

        if not delete_clicked:
            log("warn", "Delete button not found — stopping delete loop")
            break

        time.sleep(1)

        # Confirm "Delete Media" popup
        # From screenshot: popup has title "Delete Media", blue "Delete" button
        confirmed = False
        for sel in [
            'button:has-text("Delete"):visible',
            '[role="dialog"] button:has-text("Delete")',
            '.modal button:has-text("Delete")',
            'button[class*="primary"]:has-text("Delete")',
            'button[class*="blue"]:has-text("Delete")',
            'button[style*="blue"]:has-text("Delete")',
        ]:
            try:
                btn = page.locator(sel).last
                if btn.is_visible(timeout=3000):
                    btn.click()
                    confirmed = True
                    log("ok", "Delete confirmed in popup")
                    break
            except:
                continue

        if not confirmed:
            # Try by position — popup has Cancel then Delete
            try:
                popup_btns = page.locator('[role="dialog"] button, .modal button').all()
                for btn in popup_btns:
                    txt = btn.inner_text(timeout=500).strip()
                    if txt.lower() == "delete":
                        btn.click()
                        confirmed = True
                        log("ok", "Confirmed delete (by text match)")
                        break
            except:
                pass

        time.sleep(5)
        safe_wait(page, 30000)


def run_automation(folder_str: str):
    folder = Path(folder_str)
    stop_flag.clear(); otp_event.clear()
    state.update({"status":"running","log":[],"done_vins":[],"failed_vins":[],
                  "current_vin":None,"vins":[],"total":0,"step":0})

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("error", "Run: pip install playwright && playwright install chromium")
        state["status"] = "error"; return

    # ── Step 1 ────────────────────────────────────────────────────────────────
    set_step(1)
    log("info", f"Scanning: {folder}")
    unzip_vins(folder)
    if stop_flag.is_set(): state["status"] = "stopped"; return

    vins = get_vin_folders(folder)
    if not vins:
        log("error", "No VIN folders with images found")
        state["status"] = "error"; return

    state["vins"]  = vins
    state["total"] = len(vins)
    log("ok", f"Found {len(vins)} VINs")
    for v in vins:
        imgs = [f for f in (folder/v).iterdir() if f.suffix.lower() in IMG_EXTS]
        log("info", f"  {v} — {len(imgs)} image(s)")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        ctx  = browser.new_context(no_viewport=True)
        page = ctx.new_page()
        page.set_default_timeout(60000)

        # ── Step 2: Login ─────────────────────────────────────────────────────
        set_step(2)
        log("info", f"Opening: {DMS_URL}")
        page.goto(DMS_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        try:
            page.fill('input[type="email"],input[name="email"],input[placeholder*="email" i],input[placeholder*="user" i]',
                      DMS_USER, timeout=10000)
            page.fill('input[type="password"]', DMS_PASS, timeout=5000)
            page.click('button[type="submit"],button:has-text("Login"),button:has-text("Sign in")', timeout=5000)
            log("ok", "Credentials submitted")
        except Exception as e:
            log("warn", f"Auto-fill failed — fill manually ({e})")

        # ── Step 3: OTP ───────────────────────────────────────────────────────
        set_step(3)
        state["status"] = "otp_wait"
        log("warn", "PAUSED — Enter OTP in browser then click 'OTP entered' in UI")
        otp_event.wait()
        if stop_flag.is_set(): browser.close(); state["status"] = "stopped"; return
        state["status"] = "running"
        log("ok", "OTP confirmed — waiting for dashboard...")
        safe_wait(page, 60000)
        time.sleep(4)

        # ── Step 4: Vehicle Inventory ─────────────────────────────────────────
        set_step(4)
        log("info", "Navigating to Vehicle Inventory...")
        try:
            page.goto("https://app.tekioncloud.com/vi/vehicles",
                      wait_until="domcontentloaded", timeout=60000)
            safe_wait(page, 30000)
            time.sleep(3)
            log("ok", "Vehicle Inventory loaded")
        except Exception as e:
            log("warn", f"Direct URL nav failed ({e}) — navigate manually then click Resume")
            state["status"] = "otp_wait"
            otp_event.clear(); otp_event.wait()
            state["status"] = "running"
            safe_wait(page, 30000); time.sleep(3)

        # ── Steps 5-7: Per-VIN loop ───────────────────────────────────────────
        for vin in vins:
            if stop_flag.is_set(): break
            state["current_vin"] = vin
            log("info", f"━━━ VIN: {vin} ━━━")

            vin_folder = folder / vin
            images = sorted([f for f in vin_folder.iterdir() if f.suffix.lower() in IMG_EXTS])
            if not images:
                log("warn", f"No images for {vin} — skipping")
                state["failed_vins"].append(vin); continue

            try:
                # ── Search VIN ────────────────────────────────────────────────
                set_step(5)
                log("info", f"Searching: {vin}")

                # Go back to inventory list
                if "vi/vehicles" not in page.url or "vehicle/" in page.url:
                    page.goto("https://app.tekioncloud.com/vi/vehicles",
                              wait_until="domcontentloaded", timeout=60000)
                    safe_wait(page, 30000); time.sleep(3)

                # Click the inventory search box — placeholder is exactly "Search..."
                # NOT the top "Search here..." bar
                search_done = False
                try:
                    all_inputs = page.locator('input').all()
                    for inp in all_inputs:
                        ph = (inp.get_attribute("placeholder") or "").strip()
                        if ph in ("Search...", "Search…"):
                            inp.click(timeout=3000)
                            search_done = True
                            log("info", "Clicked inventory search box")
                            break
                except: pass

                if not search_done:
                    try:
                        page.locator('input[placeholder*="Search" i]').last.click(timeout=5000)
                        log("info", "Clicked search (fallback)")
                    except: pass

                time.sleep(0.3)
                page.keyboard.press("Meta+a")
                page.keyboard.press("Backspace")
                page.keyboard.type(vin, delay=50)
                log("ok", f"Typed: {vin}")
                safe_wait(page, 20000); time.sleep(2)

                # Click VIN result row
                clicked = False
                for sel in [f'td:has-text("{vin}")', f'tr:has-text("{vin}")',
                            f'[title="{vin}"]', f'text={vin}']:
                    try:
                        page.locator(sel).first.click(timeout=5000)
                        clicked = True; log("ok", "Opened VIN record"); break
                    except: continue

                if not clicked:
                    log("error", f"Could not open VIN record — skipping {vin}")
                    state["failed_vins"].append(vin); continue

                safe_wait(page, 30000); time.sleep(3)

                # ── Media tab ─────────────────────────────────────────────────
                for sel in ['[role="tab"]:has-text("Media")', 'text=Media',
                            'button:has-text("Media")', 'a:has-text("Media")']:
                    try:
                        page.locator(sel).first.click(timeout=5000)
                        log("ok", "Opened Media tab"); break
                    except: continue

                safe_wait(page, 20000); time.sleep(3)

                # ── Delete existing media ─────────────────────────────────────
                delete_all_media(page)

                # ── Upload new images ─────────────────────────────────────────
                set_step(6)
                log("info", f"Uploading {len(images)} image(s) for {vin}...")

                # Click Upload Media button
                # From screenshot: button says "Upload Media" with upload icon, center of page
                upload_done = False
                for sel in ['button:has-text("Upload Media")', 'text=Upload Media',
                            '[class*="upload-media"]', 'button:has-text("Upload")']:
                    try:
                        page.locator(sel).first.click(timeout=5000)
                        upload_done = True
                        log("ok", "Upload Media clicked"); break
                    except: continue

                if not upload_done:
                    log("error", f"Upload Media button not found for {vin}")
                    state["failed_vins"].append(vin); continue

                time.sleep(1)

                # The file chooser opens — set files directly by path
                # Playwright set_files() handles this — no need to navigate in dialog
                # It sets the files directly to the input element
                try:
                    with page.expect_file_chooser(timeout=10000) as fc_info:
                        # File chooser may open from the Upload Media click
                        # or may need a secondary click on file input
                        try:
                            page.locator('input[type="file"]').first.click(timeout=3000)
                        except:
                            pass
                    fc_info.value.set_files([str(img) for img in images])
                    log("ok", f"Set {len(images)} files via file chooser")
                except Exception as e:
                    log("warn", f"File chooser attempt 2: {e}")
                    # Retry — click Upload Media again to trigger file chooser
                    try:
                        with page.expect_file_chooser(timeout=15000) as fc_info:
                            for sel in ['button:has-text("Upload Media")',
                                        'text=Upload Media', 'button:has-text("Upload")']:
                                try:
                                    page.locator(sel).first.click(timeout=3000)
                                    break
                                except: continue
                        fc_info.value.set_files([str(img) for img in images])
                        log("ok", f"Set {len(images)} files (retry)")
                    except Exception as e2:
                        log("error", f"File chooser failed: {e2}")
                        state["failed_vins"].append(vin); continue

                log("info", "Waiting for upload to complete...")
                safe_wait(page, 120000)
                time.sleep(5)

                # ── Save ──────────────────────────────────────────────────────
                set_step(7)
                log("info", "Saving...")
                for attempt in range(SAVE_RETRIES):
                    if stop_flag.is_set(): break

                    # Dismiss OK/Okay popup
                    for ok_text in ["Okay", "OK", "Ok"]:
                        try:
                            btn = page.locator(f'button:has-text("{ok_text}")').first
                            if btn.is_visible(timeout=1500):
                                btn.click()
                                log("info", "Dismissed popup"); time.sleep(2)
                        except: pass

                    # Save button
                    try:
                        save = page.locator('button:has-text("Save")').first
                        if not save.is_visible(timeout=2000):
                            log("ok", "Returned to inventory — saved!")
                            break
                        save.click()
                        log("info", f"Save clicked (attempt {attempt+1})")
                        safe_wait(page, 30000); time.sleep(2)
                    except:
                        log("ok", "Save done"); break

                state["done_vins"].append(vin)
                log("ok", f"✓ {vin} complete!")

            except Exception as e:
                log("error", f"✗ {vin} failed: {e}")
                state["failed_vins"].append(vin)
            finally:
                state["current_vin"] = None
                time.sleep(1)

        browser.close()

    d, f = len(state["done_vins"]), len(state["failed_vins"])
    log("ok", f"━━━ All done — {d} succeeded, {f} failed ━━━")
    state["status"] = "done"; state["step"] = 8


def open_browser(port):
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{port}")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def _file(self, path, ct):
        try:
            body = Path(path).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        except: self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._file(Path(__file__).parent / "ui" / "index.html", "text/html")
        elif path == "/state":   self._json(state)
        elif path == "/stop":
            stop_flag.set(); otp_event.set()
            state["status"] = "stopped"; self._json({"ok": True})
        elif path == "/otp_done":
            otp_event.set(); self._json({"ok": True})
        elif path == "/reset":
            state.update({"status":"idle","step":0,"log":[],"vins":[],"current_vin":None,
                          "done_vins":[],"failed_vins":[],"total":0})
            stop_flag.clear(); otp_event.clear(); self._json({"ok": True})
        elif path == "/config":
            try: self._json(json.loads(CONFIG_PATH.read_text()))
            except: self._json({})
        else: self.send_error(404)

    def do_POST(self):
        path   = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length)) if length else {}
        if path == "/start":
            folder = body.get("folder", "").strip()
            if not folder or not Path(folder).is_dir():
                self._json({"ok": False, "error": f"Folder not found: {folder}"}, 400); return
            global automation_thread
            if automation_thread and automation_thread.is_alive():
                self._json({"ok": False, "error": "Already running"}); return
            stop_flag.clear(); otp_event.clear()
            automation_thread = threading.Thread(target=run_automation, args=(folder,), daemon=True)
            automation_thread.start(); self._json({"ok": True})
        else: self.send_error(404)


if __name__ == "__main__":
    print(f"\n  DMS Upload Automation — Spyne")
    print(f"  http://localhost:{PORT}\n")
    server = HTTPServer(("localhost", PORT), Handler)
    threading.Thread(target=open_browser, args=(PORT,), daemon=True).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print("\n  Stopped.")
