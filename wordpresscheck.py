import csv
import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )
}


def detect_wordpress(url: str, timeout: int = 12) -> str:
    checked_url = url

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True
        )
        checked_url = response.url
        html = response.text.lower()

        if response.status_code >= 400:
            return "unknown"

        soup = BeautifulSoup(response.text, "html.parser")
        score = 0

        if "wp-content" in html:
            score += 3

        if "wp-includes" in html:
            score += 3

        if "wordpress" in html and "wp-content" not in html and "wp-includes" not in html:
            score += 1

        meta_generator = soup.find("meta", attrs={"name": "generator"})
        if meta_generator:
            content = (meta_generator.get("content") or "").lower()
            if "wordpress" in content:
                score += 4

        for link in soup.find_all(["link", "script", "img"]):
            attr = link.get("href") or link.get("src") or ""
            attr = attr.lower()
            if "wp-content" in attr or "wp-includes" in attr:
                score += 2
                break

        rest_api = urljoin(checked_url, "/wp-json/")
        try:
            api_resp = requests.get(
                rest_api,
                headers=HEADERS,
                timeout=timeout
            )
            api_text = api_resp.text.lower()

            if api_resp.status_code == 200 and (
                "wp-json" in api_text or
                "wordpress" in api_text or
                "namespaces" in api_text
            ):
                score += 4
        except Exception:
            pass

        login_url = urljoin(checked_url, "/wp-login.php")
        try:
            login_resp = requests.get(
                login_url,
                headers=HEADERS,
                timeout=timeout
            )
            login_text = login_resp.text.lower()

            if login_resp.status_code == 200 and (
                "user_login" in login_text or
                "wp-submit" in login_text or
                "wordpress" in login_text
            ):
                score += 2
        except Exception:
            pass

        if score >= 4:
            return "yes"
        elif score >= 2:
            return "probably"
        else:
            return "no"

    except requests.RequestException:
        return "unknown"


def find_url_column(fieldnames):
    if not fieldnames:
        return None

    preferred = ["url", "final_url", "link", "adres"]
    lowered = {name.lower(): name for name in fieldnames}

    for col in preferred:
        if col in lowered:
            return lowered[col]

    return fieldnames[0]


def check_csv_for_wordpress(input_csv: str, output_csv: str = "wordpress_only.csv"):
    matching_urls = []

    with open(input_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        url_column = find_url_column(reader.fieldnames)
        if not url_column:
            print("Nie udało się znaleźć kolumny z URL.")
            return

        for i, row in enumerate(reader, start=1):
            url = (row.get(url_column) or "").strip()

            if not url:
                continue

            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            print(f"[{i}] Sprawdzam: {url}")
            result = detect_wordpress(url)

            if result in {"yes", "probably"}:
                matching_urls.append({"url": url})

    if not matching_urls:
        print("Brak pasujących linków do zapisania.")
        return

    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["url"])
        writer.writeheader()
        writer.writerows(matching_urls)

    print(f"\nGotowe. Zapisano wynik do: {output_csv}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie:")
        print("python check_wordpress.py linki.csv [wynik.csv]")
        sys.exit(1)

    input_csv = sys.argv[1]
    output_csv = sys.argv[2] if len(sys.argv) >= 3 else "wordpress_only.csv"

    check_csv_for_wordpress(input_csv, output_csv)