import csv
import os
import sys
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from ddgs import DDGS


def normalize_url(url: str) -> str:
    """
    Ujednolica URL, żeby łatwiej wykrywać duplikaty.
    Usuwa np. UTM-y, końcowy slash i normalizuje domenę.
    """
    parsed = urlparse(url)

    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/")

    # Usuwamy typowe parametry śledzące
    tracking_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "msclkid"
    }

    query_params = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in tracking_params
    ]
    query = urlencode(query_params, doseq=True)

    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    return normalized


def load_existing_urls(csv_file: str) -> set:
    existing = set()

    if not os.path.exists(csv_file):
        return existing

    with open(csv_file, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("normalized_url")
            if not url and row.get("url"):
                url = normalize_url(row["url"])
            if url:
                existing.add(url)

    return existing


def scrape_links(keyword: str, max_results: int = 50) -> list:
    rows = []

    with DDGS() as ddgs:
        results = ddgs.text(keyword, max_results=max_results)

        for i, result in enumerate(results, start=1):
            url = result.get("href") or result.get("url")
            if not url:
                continue

            rows.append({
                "keyword": keyword,
                "position_for_keyword": i,
                "url": url,
                "normalized_url": normalize_url(url),
            })

    return rows


def append_unique_links(keyword: str, max_results: int = 50, output_file: str = "linki.csv"):
    existing_urls = load_existing_urls(output_file)
    scraped_rows = scrape_links(keyword, max_results=max_results)

    new_rows = []
    skipped = 0

    for row in scraped_rows:
        if row["normalized_url"] in existing_urls:
            skipped += 1
            continue

        new_rows.append(row)
        existing_urls.add(row["normalized_url"])

    file_exists = os.path.exists(output_file)

    with open(output_file, "a", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["keyword", "position_for_keyword", "url", "normalized_url"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        writer.writerows(new_rows)

    print(f"Keyword: {keyword}")
    print(f"Znaleziono: {len(scraped_rows)}")
    print(f"Dodano nowych: {len(new_rows)}")
    print(f"Pominięto duplikatów: {skipped}")
    print(f"Plik: {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie:")
        print('python scraper.py "organizacja eventow warszawa" [liczba_wynikow] [plik.csv]')
        sys.exit(1)

    keyword = sys.argv[1]
    max_results = int(sys.argv[2]) if len(sys.argv) >= 3 else 50
    output_file = sys.argv[3] if len(sys.argv) >= 4 else "linki.csv"

    append_unique_links(keyword, max_results, output_file)