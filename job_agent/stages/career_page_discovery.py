"""Stage 3: career page discovery.

Given a company's homepage URL, returns a single validated URL for its
careers/jobs page. Three-step fallback chain, cheapest/most-reliable signal
first:

1. Fetch the homepage, extract every link's (anchor text, absolute URL), ask
   an LLM which one (if any) is the careers/jobs page.
2. If none matched: try common path guesses (/careers, /jobs, /join-us, ...)
   against the company's domain, each verified by the LLM before accepting.
3. If that also fails: search DuckDuckGo for `site:domain careers` (no API
   key needed — same zero-vendor-risk call as the Phase 2 LinkedIn mock), and
   verify the top results with the LLM before accepting.

Every fetch and LLM call is best-effort: a single company's homepage being
unreachable, or the LLM being unavailable, returns None instead of crashing a
run that's processing many companies.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from job_agent.llm import call_llm
from job_agent.models import CareerPage, Company

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

COMMON_CAREER_PATHS = [
    "/careers", "/careers/", "/jobs", "/jobs/", "/join-us", "/join-us/",
    "/work-with-us", "/about/careers", "/company/careers", "/company/jobs",
    "/en/careers", "/careers.html",
]


def _fetch(url: str) -> str | None:
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


def _extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
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

        if len(links) >= MAX_LINKS_FOR_LLM:
            break

    return links


def _classify_homepage_links(links: list[tuple[str, str]], company_name: str) -> str | None:
    """Asks the LLM to pick the careers link. Rejects any reply that isn't an
    exact match to one of the candidate URLs, to guard against hallucination."""
    if not links:
        return None

    listing = "\n".join(f"- text={text!r} url={url}" for text, url in links)
    prompt = (
        f"Below is every link found on {company_name}'s homepage, as "
        "(anchor text, URL) pairs. Identify which single URL most likely leads "
        "to the company's careers/jobs page (labels like 'Careers', 'Jobs', "
        "'Join Us', 'Work With Us', 'Open Positions', etc. — in any language).\n\n"
        f"{listing}\n\n"
        "Respond with ONLY that URL, copied exactly as it appears above, and "
        "nothing else. If none of the links look like a careers page, respond "
        "with exactly: NONE"
    )

    reply = call_llm(prompt)
    if not reply:
        return None

    reply = reply.strip()
    valid_urls = {url for _, url in links}
    return reply if reply in valid_urls else None


def _verify_career_page(url: str, company_name: str) -> bool:
    """Fetches a candidate URL and asks the LLM whether it's actually a
    careers page, so path-guessing and search-fallback results (which are
    guesses, unlike homepage-link classification) don't get accepted blind."""
    html = _fetch(url)
    if not html:
        return False

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    headings = " | ".join(h.get_text(strip=True) for h in soup.find_all(["h1", "h2"])[:5])
    body_snippet = soup.get_text(" ", strip=True)[:500]

    prompt = (
        f"Page URL: {url}\n"
        f"Page title: {title!r}\n"
        f"Headings: {headings!r}\n"
        f"Body text (first 500 chars): {body_snippet!r}\n\n"
        f"Is this {company_name}'s careers/jobs page (a page listing or "
        "linking to open positions, or clearly the entry point to one)? "
        "Respond with ONLY YES or NO."
    )

    reply = call_llm(prompt)
    return bool(reply) and reply.strip().upper().startswith("YES")


def _guess_common_paths(homepage_url: str, company_name: str) -> str | None:
    parsed = urlparse(homepage_url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    for path in COMMON_CAREER_PATHS:
        candidate = root + path
        if _fetch(candidate) is None:
            continue
        if _verify_career_page(candidate, company_name):
            return candidate

    return None


def _search_fallback(homepage_url: str, company_name: str) -> str | None:
    domain = urlparse(homepage_url).netloc

    try:
        from ddgs import DDGS
    except ImportError:
        print("WARNING: ddgs not installed — skipping search fallback (pip install ddgs).")
        return None

    query = f"site:{domain} careers"
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
    except Exception as e:
        print(f"WARNING: DuckDuckGo search failed for {query!r}: {e}")
        return None

    for result in results:
        candidate = result.get("href") or result.get("url")
        if not candidate:
            continue
        if _verify_career_page(candidate, company_name):
            return candidate

    return None


def discover(company: Company) -> CareerPage | None:
    """Returns a validated CareerPage, or None if every strategy failed."""
    html = _fetch(company.website)
    if html:
        links = _extract_links(html, company.website)
        career_url = _classify_homepage_links(links, company.name)
        if career_url:
            return CareerPage(company=company, url=career_url)

    career_url = _guess_common_paths(company.website, company.name)
    if career_url:
        return CareerPage(company=company, url=career_url)

    career_url = _search_fallback(company.website, company.name)
    if career_url:
        return CareerPage(company=company, url=career_url)

    print(f"WARNING: couldn't find a careers page for {company.name} ({company.website}).")
    return None
