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

from urllib.parse import urlparse

from bs4 import BeautifulSoup

from job_agent.html_utils import extract_links as _extract_links
from job_agent.html_utils import fetch as _fetch
from job_agent.llm import call_llm
from job_agent.models import CareerPage, Company

COMMON_CAREER_PATHS = [
    "/careers", "/careers/", "/jobs", "/jobs/", "/join-us", "/join-us/",
    "/work-with-us", "/about/careers", "/company/careers", "/company/jobs",
    "/en/careers", "/careers.html",
]


def _classify_homepage_links(links: list[tuple[str, str]], company_name: str) -> str | None:
    """Asks the LLM to pick the careers link. Rejects any reply whose URL
    isn't an exact match to one of the candidates, to guard against
    hallucination."""
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

    # Scan every line rather than requiring the whole reply to equal a
    # candidate: smaller/reasoning models don't reliably follow "respond with
    # ONLY the URL" and sometimes wrap it in extra text or enumerate one
    # verdict per candidate — the correct URL on its own line is still the
    # correct URL.
    valid_urls = {url for _, url in links}
    for line in reply.strip().splitlines():
        line = line.strip()
        if line in valid_urls:
            return line

    return None


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
    if not reply:
        return False

    # Same defensive line-scan as _classify_homepage_links: take the first
    # line that's decisively YES or NO, rather than assuming the whole reply
    # is exactly one word.
    for line in reply.strip().splitlines():
        line = line.strip().upper()
        if line.startswith("YES"):
            return True
        if line.startswith("NO"):
            return False

    return False


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
