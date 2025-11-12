import os
import time
import glob
import shutil
import requests
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.service import Service

# --- Setup folders ---
os.makedirs('downloads', exist_ok=True)

# --- Helper: extract username + videoid ---
def extract_tiktok_info(url):
    try:
        parsed = urlparse(url)
        parts = parsed.path.strip('/').split('/')
        if len(parts) >= 3 and parts[0].startswith('@') and parts[1] == 'video':
            username = parts[0][1:]
            videoid = parts[2]
            return username, videoid
    except Exception:
        pass
    return "unknown_user", "unknown_id"

# --- Download helper (with file size verification + auto retry) ---
def download_file_from_href(href, cookies, referer, tiktok_url, output_dir='downloads', max_retries=2):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Referer': referer,
    }
    session = requests.Session()
    for cookie in cookies:
        session.cookies.set(cookie['name'], cookie['value'])

    username, videoid = extract_tiktok_info(tiktok_url)
    safe_username = "".join(c for c in username if c.isalnum() or c in (' ', '_', '-')).strip() or "unknown_user"
    videoid = videoid or "unknown_id"
    parsed_href = urlparse(href)
    ext = os.path.splitext(parsed_href.path)[1] or '.mp4'
    filename = f"{safe_username} - {videoid}{ext}"
    filepath = os.path.join(output_dir, filename)

    if os.path.exists(filepath):
        print(f"    File already exists, skipping download: {filename}")
        return True

    for attempt in range(1, max_retries + 1):
        try:
            print(f"    Downloading {filename} (attempt {attempt})...")
            response = session.get(href, headers=headers, stream=True, timeout=60)
            response.raise_for_status()
            expected_size = int(response.headers.get("Content-Length", 0))

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            actual_size = os.path.getsize(filepath)
            if expected_size and actual_size + 1024 < expected_size:
                print(f"    ⚠️  Incomplete file ({actual_size} < {expected_size}) — retrying...")
                continue

            if expected_size:
                print(f"    ✅ Saved: {filepath} ({actual_size / 1024 / 1024:.1f} MB / expected {expected_size / 1024 / 1024:.1f} MB)")
            else:
                print(f"    ✅ Saved: {filepath} ({actual_size / 1024 / 1024:.1f} MB, size unknown)")
            return True

        except Exception as e:
            print(f"    Download error on attempt {attempt}: {e}")
        time.sleep(1)

    print(f"    ❌ Failed to download complete file after {max_retries} attempts.")
    return False

# --- Read URLs ---
with open('urls.txt', 'r', encoding='utf-8') as f:
    urls = [line.strip() for line in f if line.strip()]

if not urls:
    print("No URLs in urls.txt")
    exit()

# --- Load user directory map for skip check ---
user_map = {}
if os.path.exists('user_dir_map.txt'):
    with open('user_dir_map.txt', 'r', encoding='utf-8') as f:
        for line in f:
            if ':' in line:
                u, d = line.strip().split(':', 1)
                user_map[u.strip()] = d.strip()

# --- Gather all existing filenames from downloads and mapped directories ---
existing_files = set(os.listdir('downloads'))
base_td = r"C:\Bridge\Downloads\td"
for username, subdir in user_map.items():
    target_dir = os.path.join(base_td, subdir)
    if os.path.exists(target_dir):
        for f in os.listdir(target_dir):
            existing_files.add(f)

# --- Pre-check ---
urls_to_process = []
skipped_urls = []
for url in urls:
    username, videoid = extract_tiktok_info(url)
    safe_username = "".join(c for c in username if c.isalnum() or c in (' ', '_', '-')).strip() or "unknown_user"
    videoid = videoid or "unknown_id"
    filename = f"{safe_username} - {videoid}.mp4"
    if filename in existing_files:
        skipped_urls.append(url)
    else:
        urls_to_process.append(url)

print(f"\n=== Pre-check ===")
print(f"Total URLs loaded: {len(urls)}")
print(f"Already downloaded / will be skipped: {len(skipped_urls)}")
print(f"Remaining URLs for processing: {len(urls_to_process)}")
print("================\n")

if not urls_to_process:
    print("All URLs already downloaded! Nothing to do.")
    exit()

# --- Ask for headless mode ---
headless_input = input("Run Chrome in headless mode? (y/n): ").strip().lower()
headless_mode = (headless_input == 'y')

# --- Setup Chrome ---
service = Service('./chromedriver.exe')
options = webdriver.ChromeOptions()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--remote-debugging-port=9222')
options.add_experimental_option("prefs", {
    "download.default_directory": os.path.abspath("downloads"),
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
})
if headless_mode:
    options.add_argument("--headless=new")  # use new headless mode

try:
    driver = webdriver.Chrome(service=service, options=options)
    print(f"ChromeDriver launched successfully ({'headless' if headless_mode else 'visible'} mode)!")
except WebDriverException as e:
    print(f"Failed to launch ChromeDriver: {e}")
    print("Fix: Download matching ChromeDriver and place chromedriver.exe in script folder.")
    exit()

driver.implicitly_wait(10)
wait = WebDriverWait(driver, 20)

# --- Batch processing ---
total_urls = len(urls_to_process)
successful = 0
failed_urls = []
batch_size = 6
num_batches = (total_urls + batch_size - 1) // batch_size
initial_count = len(glob.glob('downloads/*.mp4'))

for batch_start in range(0, total_urls, batch_size):
    batch_end = min(batch_start + batch_size, total_urls)
    batch = urls_to_process[batch_start:batch_end]
    current_batch = (batch_start // batch_size) + 1
    print(f"\n--- Processing batch {current_batch}/{num_batches} (URLs {batch_start+1}-{batch_end} of {total_urls}) ---")

    try:
        driver.get("https://www.tikwm.com/originalDownloader.html")
        print(f"Page loaded! Title: '{driver.title}'")
        time.sleep(2)
    except Exception as e:
        print(f"Page load error for batch {current_batch}: {e}")
        continue

    batch_success, batch_skipped = 0, 0

    for idx, url in enumerate(batch, 1):
        username, videoid = extract_tiktok_info(url)
        safe_username = "".join(c for c in username if c.isalnum() or c in (' ', '_', '-')).strip() or "unknown_user"
        videoid = videoid or "unknown_id"
        filename = f"{safe_username} - {videoid}.mp4"
        filepath = os.path.join('downloads', filename)

        if os.path.exists(filepath):
            print(f"  [{idx}/{len(batch)}] File exists, skipping: {filename}")
            batch_skipped += 1
            continue

        print(f"  Processing URL {idx}/{len(batch)}: {url[:50]}...")
        retries, max_retries, url_success = 0, 3, False

        while retries < max_retries and not url_success:
            retries += 1
            try:
                url_input = wait.until(EC.presence_of_element_located((By.ID, "params")))
                url_input.clear()
                url_input.send_keys(url)
                submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-submit")))
                submit_btn.click()
                print(f"    Submitted URL {idx} (attempt {retries}). Waiting...")
                time.sleep(4)

                try:
                    error_box = driver.find_element(By.CSS_SELECTOR, "div.alert.alert-danger[role='alert']")
                    if "url parsing is failed" in error_box.text.lower():
                        print("    Parse failed — skipping this URL.")
                        failed_urls.append(url)
                        break
                except NoSuchElementException:
                    pass

                download_link = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.btn.btn-success[download]")))
                href = download_link.get_attribute('href')
                if not href or 'mp4' not in href.lower():
                    raise ValueError(f"Invalid href: {href}")
                cookies = driver.get_cookies()
                referer = driver.current_url
                print(f"    Extracted href: {href[:50]}...")

                if download_file_from_href(href, cookies, referer, url):
                    url_success = True
                    batch_success += 1
                    successful += 1
                    break

            except TimeoutException:
                print("    Timeout waiting for result, retrying...")
                time.sleep(5)
            except Exception as e:
                print(f"    Error on attempt {retries}: {e}")
                if retries == max_retries:
                    failed_urls.append(url)
                time.sleep(1)

        if not url_success:
            print(f"    URL {idx} failed after {max_retries} retries")
            failed_urls.append(url)
        if idx < len(batch):
            time.sleep(1)

    current_total = len(glob.glob('downloads/*.mp4')) - initial_count
    print(f"Batch {current_batch} complete ({batch_success}/{len(batch)} successful, {batch_skipped} skipped). Total processed: {current_total}/{total_urls}")

    if batch_end < total_urls:
        time.sleep(15)

# --- Move Section (auto for mapped, prompt for unmapped) ---
def load_user_map(map_file='user_dir_map.txt'):
    user_map = {}
    if os.path.exists(map_file):
        with open(map_file, 'r', encoding='utf-8') as f:
            for line in f:
                if ':' in line:
                    u, d = line.strip().split(':', 1)
                    user_map[u.strip()] = d.strip()
    return user_map

def save_user_map(user_map, map_file='user_dir_map.txt'):
    with open(map_file, 'w', encoding='utf-8') as f:
        for u, d in user_map.items():
            f.write(f"{u}:{d}\n")

def move_files_to_user_dirs(base_dir=r"C:\Bridge\Downloads\td"):
    user_map = load_user_map()
    downloads = [f for f in os.listdir('downloads') if f.lower().endswith('.mp4')]
    if not downloads:
        print("No files to move.")
        return

    print(f"\nMove downloaded files to user directories under {base_dir}?")
    resp = input("(y/n): ").strip().lower()
    if resp != 'y':
        return

    usernames = {}
    for f in downloads:
        if ' - ' in f:
            u = f.split(' - ')[0].strip()
            usernames.setdefault(u, []).append(f)
        else:
            usernames.setdefault('unknown_user', []).append(f)

    moved, replaced, skipped = 0, 0, 0

    # Auto-move for mapped users
    for username, files in list(usernames.items()):
        if username in user_map:
            subdir = user_map[username]
            dest_dir = os.path.join(base_dir, subdir)
            os.makedirs(dest_dir, exist_ok=True)
            print(f"\nAuto-moving {len(files)} file(s) for '{username}' to '{dest_dir}'...")
            for fname in files:
                src = os.path.join('downloads', fname)
                dst = os.path.join(dest_dir, fname)
                if os.path.exists(dst):
                    src_size = os.path.getsize(src)
                    dst_size = os.path.getsize(dst)
                    if src_size == dst_size:
                        shutil.move(src, dst)
                        replaced += 1
                        print(f"  Replaced existing (same size): {fname}")
                    else:
                        skipped += 1
                        print(f"  Skipped (size mismatch): {fname}")
                else:
                    shutil.move(src, dst)
                    moved += 1
                    print(f"  Moved: {fname}")
            del usernames[username]

    # Ask for unmapped users
    for username, files in usernames.items():
        print(f"\n=== User: {username} ===")
        subdir = input(f"Enter directory under td for '{username}': ").strip()
        if not subdir:
            print("  Skipped (no directory provided).")
            continue
        user_map[username] = subdir
        dest_dir = os.path.join(base_dir, subdir)
        os.makedirs(dest_dir, exist_ok=True)
        for fname in files:
            src = os.path.join('downloads', fname)
            dst = os.path.join(dest_dir, fname)
            shutil.move(src, dst)
            moved += 1
            print(f"  Moved: {fname}")

    save_user_map(user_map)
    print(f"\nMove summary: {moved} moved, {replaced} replaced, {skipped} skipped.")
    print("User directory mappings saved to user_dir_map.txt\n")

# --- Summary ---
print(f"\nAutomation complete! Successful: {successful}/{total_urls}")
failed_count = len(failed_urls)
print(f"Failed: {failed_count}/{total_urls}")

if failed_count > 0:
    resp = input(f"\nGenerate failed_urls.txt? (y/n): ").strip().lower()
    if resp == 'y':
        with open('failed_urls.txt', 'w', encoding='utf-8') as f:
            for u in failed_urls:
                f.write(u + '\n')
        print("Generated failed_urls.txt")

# --- Move downloaded files ---
move_files_to_user_dirs()

input("\nPress Enter to close...")
driver.quit()
