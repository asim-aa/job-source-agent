# AI Job Source Agent

Turns LinkedIn job postings into direct links to the same jobs on each company's
own career page: `company_name, career_page_url, open_position_url`.

## Phase 1 — Scope & architecture

**Pipeline: four discrete stages**, each its own module under `job_agent/stages/`:

1. `linkedin_ingestion.py` — LinkedIn job listings -> `{company_name, company_website}`
2. `company_resolution.py` — normalize/validate the website URL before crawling it
3. `career_page_discovery.py` — company website -> its careers/jobs page
4. `job_extraction.py` — careers page -> one open position's URL

**Orchestration:** a plain sequential Python function (`job_agent/pipeline.py`),
not an agent framework. The only "agent" behavior — an LLM deciding which link
on a page to follow — is scoped to stage 3; the loop that calls stage 1 then 2
then 3 then 4 is ordinary code.

**Web agent stack (stage 3):** LLM-first, not regex-heuristic-first — see
Phase 3 below for why. Homepages are fetched as static HTML (`requests` +
BeautifulSoup), not rendered with Playwright/a browser; that's a reasonable
later upgrade if a company's nav is client-side-rendered and the static fetch
comes back without the careers link in the HTML at all.

**Stage 2 is stubbed** (`NotImplementedError` with a docstring) — this repo
currently implements Phase 1 (this scaffold), Phase 2 (stage 1), Phase 3
(stage 3), and Phase 4 (stage 4). The pipeline goes straight from ingestion to
career page discovery on the raw (name, website) LinkedIn returned.

## Phase 2 — LinkedIn ingestion

`job_agent/stages/linkedin_ingestion.py` defines `LinkedInProvider`, a one-method
interface (`fetch_companies(query, limit) -> list[Company]`) that any real
scraping API (Proxycurl, Bright Data, a RapidAPI listing, ...) would implement
the same way.

**Provider used right now: `MockLinkedInProvider`**, reading canned listings from
`job_agent/fixtures/linkedin_job_listings.json` instead of calling a paid API.
This was a deliberate choice over Proxycurl/Bright Data for this stage of the
project: it avoids per-call pricing and vendor risk while the rest of the
pipeline (stages 2-4, where the actual engineering complexity lives) is still
being built, costs $0, and the fixture uses real company names and real career
websites so the ingestion output is realistic. Swapping in a real provider later
is a one-file change: implement `LinkedInProvider`, register it in
`get_provider()`, set `LINKEDIN_PROVIDER` in `.env`.

### Run it

```bash
pip install -r requirements.txt
python run_phase2_demo.py
python run_phase2_demo.py --query "engineer" --limit 5
```

Runs the tests:

```bash
pytest
```

## Phase 3 — Career page discovery

`job_agent/stages/career_page_discovery.py`'s `discover(company) -> CareerPage | None`
runs a three-step fallback chain, cheapest/most-reliable signal first:

1. **Homepage link classification.** Fetch the homepage, extract every
   `(anchor text, absolute URL)` pair, hand the whole list to an LLM and ask
   which one is the careers page. The LLM's reply is only accepted if it
   exactly matches one of the candidate URLs — a free-text reply that doesn't
   match anything actually on the page is treated as a hallucination, not a
   result.
2. **Common path guesses.** If nothing on the homepage matched, try
   `/careers`, `/jobs`, `/join-us`, etc. against the domain. Each one that
   responds gets a second LLM call — title/headings/body snippet — asking
   "is this actually a careers page?" before it's accepted; unlike step 1,
   a 200 response alone isn't good enough evidence.
3. **Search fallback.** If path guessing also comes up empty, search
   DuckDuckGo (via the `ddgs` package — no API key, same zero-vendor-risk
   call as the Phase 2 LinkedIn mock) for `site:domain careers` and
   LLM-verify the top results the same way as step 2.

**LLM backend:** `job_agent/llm.py`, same two-provider pattern as the sibling
Spotify project's `insights.py` — `LLM_PROVIDER=anthropic` (default) or
`supportvectors` (an OpenAI-compatible gateway, e.g. a bootcamp-provided
endpoint), picked via env var, never silently falling back from one to the
other. Every LLM call returns `None` with a printed warning on failure
(missing key, rate limit, network error, empty response) instead of raising,
so one bad classification degrades to "couldn't find a careers page for X"
rather than crashing a run over many companies.

### Run it

```bash
# needs ANTHROPIC_API_KEY (or the SUPPORTVECTORS_* vars) set in .env
python run_phase3_demo.py
python run_phase3_demo.py --query "engineer" --limit 3
```

Tests (`tests/test_career_page_discovery.py`) mock both `_fetch` and
`call_llm`, so `pytest` never makes a real network or LLM call.

## Phase 4 — Open position extraction

`job_agent/stages/job_extraction.py`'s `extract_one(career_page) -> JobPosting | None`,
cheapest/most-reliable signal first:

1. **ATS special-casing.** A large share of career pages route through
   Greenhouse, Lever, Ashby, or Workday — detected either directly from the
   career page URL, from a plain `<a>` linking straight to one of those
   domains, or from an `<iframe>` embedding one on an otherwise custom page.
   Each exposes a public jobs API (`boards-api.greenhouse.io`,
   `api.lever.co`, `api.ashbyhq.com`, Workday's `/wday/cxs/.../jobs`), which
   is more reliable than scraping + LLM classification: no rendering needed,
   and every result is already a real, currently-open posting.
2. **Generic fallback, static HTML.** Fetch the page, extract every link, ask
   the LLM to classify: a specific job posting, a "listing" link worth
   following one hop further (very common — a company's own in-house "/jobs"
   page, or a "browse all roles" link, is usually not itself a specific
   posting), or neither.
3. **One-hop follow.** If step 2 found a listing link, repeat step 2 against
   that page. Capped at one hop — career page -> listing page -> job posting
   covers the common real-world depth.
4. **Generic fallback, JS-rendered.** Career (and listing) pages are often
   SPAs that render job content client-side, so a plain `requests.get` can
   return an empty shell. Render with headless Chromium (Playwright) and
   repeat step 2 against the fully-rendered HTML.

**A real bug this surfaced, worth calling out:** the LLM classification
prompt lists every candidate link and asks for one verdict. Smaller/reasoning
models (this was hit against `LLM_PROVIDER=supportvectors`) don't reliably
follow "respond in exactly one line" — observed behavior was one verdict
*per candidate link* (dozens of `NONE`s with the correct answer buried in the
middle). The original parser checked only whether the *whole reply* matched
the expected format, so correct answers were silently discarded. Fixed by
scanning every line of the reply instead of assuming a single-line response —
same fix applied to stage 3's classifier. `temperature=0` was also added to
both LLM providers (classification should be deterministic, not creative).
Separately, Playwright's `networkidle` wait hung indefinitely on pages with
continuous background polling (analytics beacons, etc. — Stripe's careers
page is one); switched to `domcontentloaded` plus a fixed render pause.

### Run it

```bash
# needs playwright's browser binary installed once:
playwright install chromium
python run_phase4_demo.py   # career page -> job URL only, no CSV
```

Tests (`tests/test_job_extraction.py`) mock `_fetch`, `_try_ats`,
`call_llm`, and `_render_with_playwright`, so `pytest` never makes a real
network, ATS API, or LLM call.

## Phase 5 — Output formatting & aggregation

`job_agent/pipeline.py`'s `run_pipeline(...)` chains stages 1 -> 3 -> 4 and
`job_agent/output.py`'s `write_csv(...)` normalizes results into the required
`company_name, career_page_url, job_url` CSV rows. Per-company failures (no
career page found, no open position found) are logged and that company is
dropped from the results — one uncooperative site must not stop the run for
the rest, which is the whole point of "generic across different site formats."

### Run it

```bash
python run_pipeline.py                                    # results.csv
python run_pipeline.py --query "engineer" --limit 3 --out results.csv
```

Live-verified against 5 real companies (Anthropic, Stripe, Figma, Notion,
Duolingo) covering three different resolution paths — a direct ATS link
(Figma, Notion), a same-domain "/jobs" page found without any hop (Duolingo),
and a one-hop "browse open roles" -> listing page (Anthropic, Stripe) — 5/5
correct across two consecutive runs.

Tests (`tests/test_pipeline.py`, `tests/test_output.py`) mock `discover` and
`extract_one`, so `pytest` never makes a real network or LLM call.

## Roadmap

- Phase 6 (optional): implement `company_resolution.py` (URL normalization/
  validation between stages 1 and 3)
- Demo video showing the pipeline end-to-end against real company sites
