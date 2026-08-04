"""Stage 4: job URL extraction.

Given a career page, returns one open position's URL. Cheapest/most-reliable
signal first, same philosophy as stage 3:

1. ATS special-casing. A large share of career pages route through Greenhouse,
   Lever, Ashby, or Workday — either directly (the career page URL itself is
   hosted on one of them) or via an <iframe> embedding one on an otherwise
   custom page. Each of these exposes a public jobs API, which is far more
   reliable than scraping + LLM classification: no rendering needed, and every
   result is already a real, currently-open posting (no "is this legit"
   judgment call required).
2. Generic fallback, static HTML: fetch the career page as-is, extract every
   link. A plain <a> pointing at an ATS domain (not just an <iframe> — plenty
   of sites just link out to their Greenhouse/Lever/etc. board) is tried via
   the ATS path above. Otherwise, ask the LLM to classify the links: either a
   specific open position, a "listing" link worth following one hop further
   (a company's own in-house "/jobs" page, or a "browse all roles" link, is
   common and is NOT itself a specific posting), or neither.
3. One-hop follow: if step 2 found a listing link, fetch/render *that* page
   and repeat step 2 against it. Capped at one hop — career page -> listing
   page -> job posting is the common real-world depth; further chains aren't
   chased.
4. Generic fallback, JS-rendered: many career (and listing) pages are SPAs
   that render their job content client-side, so a plain `requests.get`
   returns an empty shell. Render with a headless browser (Playwright) and
   repeat step 2 against the fully-rendered HTML.

Every network/LLM call is best-effort: a single company's career page being
unreachable, having no open roles, or the LLM being unavailable, returns None
instead of crashing a run that's processing many companies.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_agent.html_utils import REQUEST_HEADERS, REQUEST_TIMEOUT
from job_agent.html_utils import extract_links as _extract_links
from job_agent.html_utils import fetch as _fetch
from job_agent.llm import call_llm
from job_agent.models import CareerPage, JobPosting

GREENHOUSE_EMBED_RE = re.compile(r"boards\.greenhouse\.io/embed/job_board\?.*\bfor=([^&\s\"']+)")
GREENHOUSE_RE = re.compile(r"(?:boards|job-boards)\.greenhouse\.io/([^/?#\s\"']+)")
LEVER_RE = re.compile(r"jobs(?:\.[a-z]{2})?\.lever\.co/([^/?#\s\"']+)")
ASHBY_RE = re.compile(r"jobs\.ashbyhq\.com/([^/?#\s\"']+)")
WORKDAY_RE = re.compile(r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com(/[^\s\"'<>]*)")

ATS_DOMAINS = ("greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com")
MAX_HOP_DEPTH = 1


def _extract_greenhouse_jobs(token: str) -> list[str]:
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    try:
        response = requests.get(api_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        jobs = response.json().get("jobs", [])
    except (requests.RequestException, ValueError) as e:
        print(f"WARNING: Greenhouse jobs API request failed for {api_url}: {e}")
        return []
    return [job["absolute_url"] for job in jobs if job.get("absolute_url")]


def _extract_lever_jobs(token: str) -> list[str]:
    api_url = f"https://api.lever.co/v0/postings/{token}?mode=json"
    try:
        response = requests.get(api_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        jobs = response.json()
    except (requests.RequestException, ValueError) as e:
        print(f"WARNING: Lever jobs API request failed for {api_url}: {e}")
        return []
    return [job["hostedUrl"] for job in jobs if job.get("hostedUrl")]


def _extract_ashby_jobs(token: str) -> list[str]:
    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{token}"
    try:
        response = requests.get(api_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        jobs = response.json().get("jobs", [])
    except (requests.RequestException, ValueError) as e:
        print(f"WARNING: Ashby jobs API request failed for {api_url}: {e}")
        return []
    return [job["jobUrl"] for job in jobs if job.get("jobUrl")]


def _extract_workday_jobs(url: str) -> list[str] | None:
    """Returns None (not []) when `url` isn't a Workday URL at all, so callers
    can distinguish "not Workday" from "Workday but the API call failed"."""
    match = WORKDAY_RE.search(url)
    if not match:
        return None

    tenant, wd_number, site_path = match.groups()
    site = site_path.strip("/").split("/")[-1] or "External"
    api_url = f"https://{tenant}.{wd_number}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"

    try:
        response = requests.post(
            api_url,
            json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""},
            headers=REQUEST_HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        postings = response.json().get("jobPostings", [])
    except (requests.RequestException, ValueError) as e:
        print(f"WARNING: Workday jobs API request failed for {api_url}: {e}")
        return []

    base = f"https://{tenant}.{wd_number}.myworkdayjobs.com"
    return [
        urljoin(base, posting["externalPath"])
        for posting in postings
        if posting.get("externalPath")
    ]


def _try_ats(url: str) -> list[str]:
    """Detects a known ATS from `url` and returns its open-position URLs, or
    [] if `url` doesn't match any known ATS (or the ATS call itself failed)."""
    match = GREENHOUSE_EMBED_RE.search(url)
    if match:
        return _extract_greenhouse_jobs(match.group(1))

    match = GREENHOUSE_RE.search(url)
    if match:
        return _extract_greenhouse_jobs(match.group(1))

    match = LEVER_RE.search(url)
    if match:
        return _extract_lever_jobs(match.group(1))

    match = ASHBY_RE.search(url)
    if match:
        return _extract_ashby_jobs(match.group(1))

    workday_jobs = _extract_workday_jobs(url)
    if workday_jobs is not None:
        return workday_jobs

    return []


def _find_ats_iframe(html: str, base_url: str) -> str | None:
    """Custom-domain career pages often just embed an ATS widget in an
    <iframe> rather than being hosted on the ATS domain directly."""
    soup = BeautifulSoup(html, "html.parser")
    for iframe in soup.find_all("iframe", src=True):
        src = urljoin(base_url, iframe["src"].strip())
        if any(domain in src for domain in ATS_DOMAINS):
            return src
    return None


def _find_ats_link(links: list[tuple[str, str]]) -> str | None:
    """Just as common as an <iframe> embed: a plain "Apply" / "See open
    roles" <a> linking straight to the company's ATS board. Free and
    deterministic, so it's tried before spending an LLM call."""
    for _, url in links:
        if any(domain in url for domain in ATS_DOMAINS):
            return url
    return None


def _classify_job_link(
    links: list[tuple[str, str]], career_page_url: str, company_name: str
) -> tuple[str, str] | None:
    """Asks the LLM to classify the links on a career/listing page. Returns
    ("job", url) for a specific open position, ("listing", url) for a page
    worth following one hop further (e.g. a company's own "/jobs" page, or a
    "browse all roles" link — common, and NOT itself a specific posting), or
    None. Rejects any reply whose URL isn't an exact match to one of the
    candidates, to guard against hallucination."""
    if not links:
        return None

    listing = "\n".join(f"- text={text!r} url={url}" for text, url in links)
    prompt = (
        f"Below is every link found on {company_name}'s careers page "
        f"({career_page_url}), as (anchor text, URL) pairs.\n\n"
        f"{listing}\n\n"
        "Classify these links and respond in EXACTLY one of these three "
        "formats, nothing else:\n"
        "  JOB: <url>     one link points directly to a single, specific, "
        "currently-open job posting (e.g. one role like 'Software Engineer').\n"
        "  LISTING: <url>  no link is a specific posting, but one clearly "
        "leads to a fuller list of open positions (an ATS board, a '/jobs' "
        "page, a 'browse all roles' link) — and that URL is DIFFERENT from "
        f"this page's own URL ({career_page_url}).\n"
        "  NONE            neither applies.\n"
        "Copy <url> exactly as it appears above."
    )

    reply = call_llm(prompt)
    if not reply:
        return None

    # Scan every line rather than just checking the reply's overall prefix:
    # smaller/reasoning models don't reliably follow "respond in exactly one
    # line" and sometimes emit one verdict per candidate link (a page's worth
    # of NONEs with the real answer buried in the middle) — the correct
    # answer showing up on line 6 of 40 is still the correct answer. JOB
    # takes priority over LISTING if a reply somehow claims both.
    valid_urls = {url for _, url in links}
    listing_url = None
    for line in reply.strip().splitlines():
        line = line.strip()
        if line.upper().startswith("JOB:"):
            candidate = line[len("JOB:"):].strip()
            if candidate in valid_urls:
                return ("job", candidate)
        elif line.upper().startswith("LISTING:") and listing_url is None:
            candidate = line[len("LISTING:"):].strip()
            if candidate in valid_urls and candidate != career_page_url:
                listing_url = candidate

    if listing_url:
        return ("listing", listing_url)

    return None


PLAYWRIGHT_NAV_TIMEOUT_MS = 20_000
# domcontentloaded fires before client-side JS has rendered content. A single
# fixed pause was tried first but proved unreliable: Robinhood's careers page
# (Greenhouse-backed) loads its job list widget on a variable delay — a fixed
# 2s pause sometimes caught it and sometimes didn't, non-deterministically.
# "networkidle" was tried before that and is worse: pages with continuous
# background polling (analytics beacons, etc.) never go idle and just time
# out. Polling until the link count stabilizes handles both cases: fast pages
# don't pay extra wait, slow ones get the time they actually need.
PLAYWRIGHT_POLL_INTERVAL_MS = 500
PLAYWRIGHT_MAX_SETTLE_WAIT_MS = 6_000


def _wait_for_content_to_settle(page) -> None:
    last_count = -1
    elapsed = 0
    while elapsed < PLAYWRIGHT_MAX_SETTLE_WAIT_MS:
        page.wait_for_timeout(PLAYWRIGHT_POLL_INTERVAL_MS)
        elapsed += PLAYWRIGHT_POLL_INTERVAL_MS
        count = page.evaluate("document.querySelectorAll('a').length")
        if count == last_count:
            return
        last_count = count


def _render_with_playwright(url: str) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "WARNING: playwright not installed — skipping JS-rendered fallback "
            "(pip install playwright && playwright install chromium)."
        )
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=REQUEST_HEADERS["User-Agent"])
                page.goto(url, timeout=PLAYWRIGHT_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
                _wait_for_content_to_settle(page)
                return page.content()
            finally:
                browser.close()
    except Exception as e:
        print(f"WARNING: Playwright render failed for {url}: {e}")
        return None


def _from_html(html: str, career_page: CareerPage, depth: int = 0) -> JobPosting | None:
    iframe_src = _find_ats_iframe(html, career_page.url)
    if iframe_src:
        ats_jobs = _try_ats(iframe_src)
        if ats_jobs:
            return JobPosting(career_page=career_page, url=ats_jobs[0])

    links = _extract_links(html, career_page.url)

    ats_link = _find_ats_link(links)
    if ats_link:
        ats_jobs = _try_ats(ats_link)
        if ats_jobs:
            return JobPosting(career_page=career_page, url=ats_jobs[0])

    classification = _classify_job_link(links, career_page.url, career_page.company.name)
    if classification is None:
        return None

    kind, url = classification
    if kind == "job":
        return JobPosting(career_page=career_page, url=url)

    if depth >= MAX_HOP_DEPTH:
        return None
    return _follow_listing_link(url, career_page, depth)


def _follow_listing_link(url: str, career_page: CareerPage, depth: int) -> JobPosting | None:
    ats_jobs = _try_ats(url)
    if ats_jobs:
        return JobPosting(career_page=career_page, url=ats_jobs[0])

    html = _fetch(url)
    if html:
        result = _from_html(html, career_page, depth=depth + 1)
        if result:
            return result

    rendered = _render_with_playwright(url)
    if rendered:
        result = _from_html(rendered, career_page, depth=depth + 1)
        if result:
            return result

    return None


def extract_one(career_page: CareerPage) -> JobPosting | None:
    """Returns a validated JobPosting, or None if every strategy failed."""
    ats_jobs = _try_ats(career_page.url)
    if ats_jobs:
        return JobPosting(career_page=career_page, url=ats_jobs[0])

    html = _fetch(career_page.url)
    if html:
        result = _from_html(html, career_page)
        if result:
            return result

    rendered_html = _render_with_playwright(career_page.url)
    if rendered_html:
        result = _from_html(rendered_html, career_page)
        if result:
            return result

    print(
        f"WARNING: couldn't find an open position for {career_page.company.name} "
        f"({career_page.url})."
    )
    return None
