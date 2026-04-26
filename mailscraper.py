import re
import csv
import time
import multiprocessing as mp
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

CONTACT_HINTS = [
    "contact", "kontakt", "about", "o-nas", "about-us",
    "team", "support", "help", "company", "event", "eventy"
]

REQUEST_TIMEOUT = 4
HARD_URL_TIMEOUT = 5
MAX_SUBPAGES = 2
SLEEP_BETWEEN_URLS = 0.1


def normalize_email(email: str) -> str:
    email = unquote(email).strip().lower()
    email = email.replace("mailto:", "")
    email = email.replace("http://", "").replace("https://", "")
    email = email.lstrip("/").strip()
    email = email.rstrip(".,;:)]}>\"'")
    email = email.lstrip("([<{\"'")
    return email


def is_valid_email(email: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", email))


def extract_emails_from_text(text: str) -> set[str]:
    emails = set()
    for match in EMAIL_RE.findall(text or ""):
        email = normalize_email(match)
        if is_valid_email(email):
            emails.add(email)
    return emails


def get_html(url: str) -> str:
    r = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    r.raise_for_status()
    return r.text


def same_domain(url1: str, url2: str) -> bool:
    return urlparse(url1).netloc.lower() == urlparse(url2).netloc.lower()


def extract_emails_from_mailto(soup: BeautifulSoup) -> set[str]:
    emails = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            raw = href.split(":", 1)[1].split("?", 1)[0]
            email = normalize_email(raw)
            if is_valid_email(email):
                emails.add(email)
    return emails


def find_candidate_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = (a.get_text(" ", strip=True) or "").lower()
        full_url = urljoin(base_url, href)

        if full_url.startswith("mailto:"):
            continue

        combined = f"{href} {text}".lower()
        if any(hint in combined for hint in CONTACT_HINTS) and same_domain(base_url, full_url):
            found.append(full_url)

    unique = []
    seen = set()
    for link in found:
        if link not in seen:
            seen.add(link)
            unique.append(link)

    return unique[:MAX_SUBPAGES]


def scrape_site(url: str) -> dict:
    result = {
        "url": url,
        "emails": set(),
        "checked_pages": [],
        "error": ""
    }

    try:
        html = get_html(url)
        result["checked_pages"].append(url)

        result["emails"] |= extract_emails_from_text(html)

        soup = BeautifulSoup(html, "html.parser")
        result["emails"] |= extract_emails_from_mailto(soup)

        subpages = find_candidate_links(url, html)

        for link in subpages:
            try:
                sub_html = get_html(link)
                result["checked_pages"].append(link)

                result["emails"] |= extract_emails_from_text(sub_html)

                sub_soup = BeautifulSoup(sub_html, "html.parser")
                result["emails"] |= extract_emails_from_mailto(sub_soup)

            except Exception as e:
                msg = f"Podstrona {link}: {type(e).__name__}: {e}"
                if result["error"]:
                    result["error"] += " || " + msg
                else:
                    result["error"] = msg

    except Exception as e:
        result["error"] = f"Strona główna {url}: {type(e).__name__}: {e}"

    result["emails"] = sorted(result["emails"])
    return result


def worker(url: str, queue: mp.Queue) -> None:
    try:
        data = scrape_site(url)
        queue.put(data)
    except Exception as e:
        queue.put({
            "url": url,
            "emails": [],
            "checked_pages": [],
            "error": f"Worker crash: {type(e).__name__}: {e}"
        })


def scrape_site_with_hard_timeout(url: str, hard_timeout: int = HARD_URL_TIMEOUT) -> dict:
    queue = mp.Queue()
    process = mp.Process(target=worker, args=(url, queue))
    process.start()

    process.join(hard_timeout)

    if process.is_alive():
        process.terminate()
        process.join(1)
        return {
            "url": url,
            "emails": [],
            "checked_pages": [],
            "error": f"URL pominięty: przekroczono {hard_timeout} sekund"
        }

    if not queue.empty():
        return queue.get()

    return {
        "url": url,
        "emails": [],
        "checked_pages": [],
        "error": "Brak wyniku z procesu"
    }


def read_urls_from_csv(input_file: str) -> list[str]:
    urls = []

    with open(input_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            return urls

        url_column = None
        for col in reader.fieldnames:
            if col.lower() == "url":
                url_column = col
                break

        if not url_column:
            url_column = reader.fieldnames[0]

        for row in reader:
            url = (row.get(url_column) or "").strip()
            if url:
                urls.append(url)

    return urls


def scrape_from_csv(input_file="wordpress_only.csv", output_file="emails.csv"):
    print("[INFO] Start", flush=True)

    urls = read_urls_from_csv(input_file)
    print(f"[INFO] Wczytano {len(urls)} adresów", flush=True)

    rows = []

    for raw_url in urls:
        url = raw_url
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        print(f"[INFO] Start URL: {url}", flush=True)
        started = time.time()

        data = scrape_site_with_hard_timeout(url, HARD_URL_TIMEOUT)

        elapsed = round(time.time() - started, 2)

        if data["emails"]:
            print(f"[OK] {url} | {elapsed}s | {', '.join(data['emails'])}", flush=True)
            for email in data["emails"]:
                rows.append({
                    "url": data["url"],
                    "email": email,
                    "checked_pages": " | ".join(data["checked_pages"]),
                    "error": data["error"]
                })
        else:
            print(f"[INFO] Brak maili | {url} | {elapsed}s", flush=True)
            if data["error"]:
                print(f"[ERROR] {url} | {data['error']}", flush=True)

            rows.append({
                "url": data["url"],
                "email": "",
                "checked_pages": " | ".join(data["checked_pages"]),
                "error": data["error"] or "Brak maili"
            })

        time.sleep(SLEEP_BETWEEN_URLS)

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["url", "email", "checked_pages", "error"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"[INFO] Zapisano: {output_file}", flush=True)


if __name__ == "__main__":
    mp.freeze_support()
    mp.set_start_method("spawn", force=True)
    scrape_from_csv("wordpress_only.csv", "emails.csv")