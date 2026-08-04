"""Shared HTTP fetch + link-extraction helpers for stages 3 and 4."""

from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT = 10
REQUEST_HEADERS = {
    # A default python-requests UA gets blocked by some sites; identify as a
    # real-looking browser instead.
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 JobSourceAgent/0.1"
    )
}
MAX_LINKS_FOR_LLM = 250
MAX_ANCHOR_TEXT_LEN = 80


def fetch(url: str) -> str | None:
    try:
        response = requests.get(
            url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True
        )
    except requests.RequestException as e:
        print(f"WARNING: couldn't fetch {url}: {e}")
        return None
    if response.status_code != 200:
        return None
    return response.text


def extract_links(
    html: str, base_url: str, max_links: int = MAX_LINKS_FOR_LLM
) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    links: list[tuple[str, str]] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue

        absolute = urljoin(base_url, href)
        if not absolute.startswith(("http://", "https://")):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)

        text = a.get_text(strip=True)[:MAX_ANCHOR_TEXT_LEN]
        links.append((text, absolute))

        if len(links) >= max_links:
            break

    return links
