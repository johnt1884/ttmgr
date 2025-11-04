
import time
import os
import sys
import glob
import shutil
import requests
import webbrowser
import pyperclip
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

# -------- CONFIG --------
USERNAMES_FILE = "usernames.txt"
FOUND_URLS_FILE = "found_urls.txt"
TIMEOUT = 15
SCROLL_TO_COLLECT = False
MAX_SCROLL_ATTEMPTS = 20
SCROLL_PAUSE = 1.0
DOWNLOADS_DIR = 'downloads'
BASE_TD = r"C:\Bridge\Downloads\td"
# ------------------------

def normalize_profile_url(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("@"):
        raw = raw[1:]
    raw = raw.lstrip("/")
    return f"https://www.tiktok.com/@{raw}"

def normalize_tiktok_url(url):
    parsed = urlparse(url)
    clean_path = parsed.path.rstrip('/')
    return f"https://www.tiktok.com{clean_path}"

def get_video_links_for_profile(driver, profile_url, timeout=TIMEOUT, scroll=False,
                                max_scroll_attempts=MAX_SCROLL_ATTEMPTS, scroll_pause=SCROLL_PAUSE):
    links = set()
    driver.get(profile_url)
    wait = WebDriverWait(driver, timeout)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/video/"]')))
    except Exception:
        return links
    time.sleep(0.5)

    def collect_current():
        anchors = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/video/"]')
        for a in anchors:
            href = a.get_attribute("href")
            if href:
                links.add(normalize_tiktok_url(urljoin(profile_url, href)))

    collect_current()

    if scroll:
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0
        while scroll_attempts < max_scroll_attempts:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(scroll_pause)
            collect_current()
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
            else:
                scroll_attempts = 0
                last_height = new_height
    return links

def fetch_urls():
    if not os.path.exists(USERNAMES_FILE):
        print(f"Error: {USERNAMES_FILE} not found in {os.getcwd()}")
        sys.exit(1)

    with open(USERNAMES_FILE, "r", encoding="utf-8") as f:
        raw_lines = [ln.strip() for ln in f.readlines()]

    usernames = [ln for ln in raw_lines if ln and not ln.startswith("#")]
    if not usernames:
        print("No usernames found in usernames.txt")
        sys.exit(0)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("start-maximized")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        print("ChromeDriver launched successfully!")
    except WebDriverException as e:
        print(f"Failed to launch ChromeDriver: {e}")
        print("Fix: Download matching ChromeDriver and place chromedriver.exe in script folder.")
        exit()

    all_found_urls = []
    for raw in usernames:
        profile_url = normalize_profile_url(raw)
        if not profile_url:
            continue

        print(f"[+] Visiting {profile_url}")
        try:
            found = get_video_links_for_profile(driver, profile_url, scroll=SCROLL_TO_COLLECT)
        except Exception as e:
            print(f"    ! Error while processing {profile_url}: {e}")
            found = set()

        found = sorted(found)
        all_found_urls.extend(found)
        print(f"    -> {len(found)} links found")
        time.sleep(1.0)

    driver.quit()
    return all_found_urls

def download_videos(urls_to_download):
    if not urls_to_download:
        print("No new videos to download.")
        return []

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("start-maximized")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        print("ChromeDriver for downloading launched successfully!")
    except WebDriverException as e:
        print(f"Failed to launch ChromeDriver: {e}")
        return []

    driver.implicitly_wait(10)
    wait = WebDriverWait(driver, 20)

    total_urls = len(urls_to_download)
    successful = 0
    failed_urls = []
    newly_downloaded_files = []
    batch_size = 6
    num_batches = (total_urls + batch_size - 1) // batch_size

    for batch_start in range(0, total_urls, batch_size):
        batch_end = min(batch_start + batch_size, total_urls)
        batch = urls_to_download[batch_start:batch_end]
        current_batch = (batch_start // batch_size) + 1
        print(f"\n--- Processing batch {current_batch}/{num_batches} (URLs {batch_start+1}-{batch_end} of {total_urls}) ---")

        try:
            driver.get("https://www.tikwm.com/originalDownloader.html")
            print(f"Page loaded! Title: '{driver.title}'")
            time.sleep(2)
        except Exception as e:
            print(f"Page load error for batch {current_batch}: {e}")
            failed_urls.extend(batch)
            continue

        for idx, url in enumerate(batch, 1):
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
                    
                    downloaded_filename = download_file_from_href(href, cookies, referer, url)
                    if downloaded_filename:
                        url_success = True
                        successful += 1
                        newly_downloaded_files.append(downloaded_filename)
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
                if url not in failed_urls:
                    failed_urls.append(url)
            if idx < len(batch):
                time.sleep(1)

        if batch_end < total_urls:
            time.sleep(15)

    print(f"\nDownload complete! Successful: {successful}/{total_urls}")
    failed_count = len(failed_urls)
    print(f"Failed: {failed_count}/{total_urls}")

    if failed_count > 0:
        resp = input(f"\nGenerate failed_urls.txt? (y/n): ").strip().lower()
        if resp == 'y':
            with open('failed_urls.txt', 'w', encoding='utf-8') as f:
                for u in failed_urls:
                    f.write(u + '\n')
            print("Generated failed_urls.txt")

    driver.quit()

    if newly_downloaded_files:
        generate_html_viewer(newly_downloaded_files)
        resp = input("\nOpen video viewer? (y/n): ").strip().lower()
        if resp == 'y':
            webbrowser.open('video_viewer.html')

    return newly_downloaded_files

def generate_html_viewer(downloaded_files):
    if not downloaded_files:
        print("No new videos to display.")
        return

    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
    <title>TikTok Video Viewer</title>
    <style>
        body { font-family: sans-serif; }
        .user-section { margin-bottom: 20px; }
        .video-container { display: inline-block; margin: 10px; position: relative; }
        .video-container video { width: 310px; height: 420px; }
        .video-container input[type=checkbox] { position: absolute; top: 10px; left: 10px; }
    </style>
    </head>
    <body>
    <h1>Newly Downloaded Videos</h1>
    """

    videos_by_user = {}
    for video_file in downloaded_files:
        username = video_file.split(' - ')[0]
        if username not in videos_by_user:
            videos_by_user[username] = []
        videos_by_user[username].append(video_file)

    for username, videos in videos_by_user.items():
        html_content += f'<div class="user-section"><h2>{username}</h2>'
        for video in videos:
            html_content += f"""
            <div class="video-container">
                <video controls src="{os.path.join(DOWNLOADS_DIR, video)}"></video>
                <input type="checkbox" name="video" value="{video}">
            </div>
            """
        html_content += '</div>'

    downloads_dir_abs = os.path.abspath(DOWNLOADS_DIR)
    processed_dir_abs = os.path.join(BASE_TD, 'processed')

    js_downloads_dir = downloads_dir_abs.replace('\\', '\\\\')
    js_processed_dir = processed_dir_abs.replace('\\', '\\\\')

    js_downloads_dir = os.path.abspath(DOWNLOADS_DIR).replace('\\', '\\\\')
    js_processed_dir = os.path.join(BASE_TD, 'processed').replace('\\', '\\\\')

    html_content += f"""
    <button id="process-button">Process</button>
    <script>
        const downloadsDir = "{js_downloads_dir}";
        const processedDir = "{js_processed_dir}";

        document.getElementById('process-button').addEventListener('click', () => {{
            const checkboxes = document.querySelectorAll('input[name="video"]:checked');
            const selected_videos = Array.from(checkboxes).map(cb => cb.value);
            const all_videos = Array.from(document.querySelectorAll('input[name="video"]')).map(cb => cb.value);
            const unselected_videos = all_videos.filter(video => !selected_videos.includes(video));
            
            let commands = '';
            selected_videos.forEach(video => {{
                commands += 'move "' + downloadsDir + '\\\\' + video + '" "' + processedDir + '"\\n';
            }});
            unselected_videos.forEach(video => {{
                commands += 'del "' + downloadsDir + '\\\\' + video + '"\\n';
            }});
            
            navigator.clipboard.writeText(commands).then(() => {{
                alert('Commands copied to clipboard!');
            }}, () => {{
                alert('Failed to copy commands to clipboard.');
            }});
        }});
    </script>
    </body>
    </html>
    """

    with open("video_viewer.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("Generated video_viewer.html")

def apply_clipboard_commands():
    print("Applying commands from clipboard...")
    commands = pyperclip.paste().strip().split('\n')
    for cmd in commands:
        cmd = cmd.strip()
        if not cmd:
            continue
        try:
            print(f"Executing: {cmd}")
            os.system(cmd)
        except Exception as e:
            print(f"Error executing command: {cmd}\n{e}")

def main():
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    newly_downloaded_files = []
    while True:
        print("\n--- TikTok Manager Menu ---")
        print("1. Check for New Videos")
        print("2. Open Last Video Viewer")
        print("3. Apply Commands from Clipboard")
        print("4. Exit")
        choice = input("Enter your choice: ")

        if choice == '1':
            is_first_run = not os.path.exists(FOUND_URLS_FILE)
            
            if is_first_run:
                print("First run detected. Fetching all available video URLs to create a baseline.")
                all_current_urls = fetch_urls()
                with open(FOUND_URLS_FILE, "w", encoding="utf-8") as f:
                    for url in all_current_urls:
                        f.write(url + "\n")
                print(f"Baseline URL list created at {FOUND_URLS_FILE}. No videos were downloaded.")
                print("Run 'Check for New Videos' again to find and download videos posted since now.")
                continue

            # Subsequent runs
            with open(FOUND_URLS_FILE, "r", encoding="utf-8") as f:
                previous_urls = set(
                    normalize_tiktok_url(line.strip()) for line in f
                    if line.strip() and not line.startswith("#")
                )
            
            all_current_urls = [normalize_tiktok_url(url) for url in fetch_urls()]
            print(f"\nFound {len(all_current_urls)} total URLs.")

            new_urls_to_download = set(all_current_urls) - previous_urls

            if not new_urls_to_download:
                print("No new videos found.")
                continue

            print(f"Found {len(new_urls_to_download)} new videos.")
            
            resp = input("Do you want to download them now? (y/n): ").strip().lower()

            if resp == 'y':
                newly_downloaded_files = download_videos(list(new_urls_to_download))
                
                # Update the master list ONLY after a successful download process
                with open(FOUND_URLS_FILE, "w", encoding="utf-8") as f:
                    # Write headers
                    f.write(f"# Collected TikTok video URLs\n\n")
                    # Get unique usernames from the URLs
                    usernames = set()
                    for url in all_current_urls:
                        username, _ = extract_tiktok_info(url)
                        if username != "unknown_user":
                            usernames.add(username)
                    
                    for username in sorted(list(usernames)):
                        f.write(f"### https://www.tiktok.com/@{username}\n")
                        for url in all_current_urls:
                            if f"@{username}" in url:
                                f.write(f"{url}\n")
                        f.write("\n")

                print(f"Updated URL list saved to {FOUND_URLS_FILE}")
            else:
                print("Download cancelled.")

        elif choice == '2':
            if not os.path.exists("video_viewer.html"):
                print("\nNo video viewer has been generated yet. Please download videos first.")
                continue
            webbrowser.open('video_viewer.html')
        elif choice == '3':
            apply_clipboard_commands()
        elif choice == '4':
            break
        else:
            print("Invalid choice, please try again.")

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

def download_file_from_href(href, cookies, referer, tiktok_url, output_dir=DOWNLOADS_DIR, max_retries=2):
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
        return filename

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
            return filename

        except Exception as e:
            print(f"    Download error on attempt {attempt}: {e}")
        time.sleep(1)

    print(f"    ❌ Failed to download complete file after {max_retries} attempts.")
    return None

if __name__ == "__main__":
    main()
