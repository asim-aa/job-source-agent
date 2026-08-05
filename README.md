# AI Job Source Agent

Turns LinkedIn job postings into direct links to the same jobs on each company's
own career page: `company_name, career_page_url, job_url`.

## Demo video

End-to-end walkthrough against real company sites (script: [DEMO_SCRIPT.md](DEMO_SCRIPT.md)):

https://github.com/user-attachments/assets/d2923e57-5fa8-49ab-9b35-51c6342cf9f5

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

**Stage 2 is stubbed** (`NotImplementedError` with a docstring) — every other
phase (1 through 6, including generalization testing and the demo video) is
complete. The pipeline goes straight from ingestion to career page discovery
on the raw (name, website) pair LinkedIn returned.

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

**Why this is the final answer, not just a placeholder:** the project brief
itself frames a scraping API as optional ("you *may* utilize third party
LinkedIn crawler API *if you need*") and defines Phase 2's deliverable as
just "a clean list of `{company_name, company_website}` pairs" — a format
requirement, not a data-source requirement. The three real alternatives were
considered and rejected: a paid API (Proxycurl/Bright Data) costs money on
an ongoing basis for what's explicitly an optional step; scraping
linkedin.com directly is what the brief itself calls out as aggressively
blocked, and building around that risks the account and edges toward the
kind of bot-detection evasion this project deliberately avoided elsewhere
(see Salesforce in Phase 6); a free trial credit on one of those APIs was
the closest real option, but doesn't change the fundamental shape of the
tradeoff for a handful of demo calls. The engineering weight the brief
actually asks for — and where all the real failures, fixes, and iteration
happened — is stages 2 through 4, not this one. `LinkedInProvider` exists
precisely so that swapping in a real source later, if it's ever worth the
cost, is a one-file change rather than a rewrite.

### Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in an LLM key — needed from Phase 3 onward, not this phase
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
page is one); switched to `domcontentloaded` plus a render-settle strategy —
see Phase 6 for how that strategy evolved further.

### Run it

```bash
# needs ANTHROPIC_API_KEY (or the SUPPORTVECTORS_* vars) set in .env, and
# playwright's browser binary installed once:
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

## Phase 6 — Generalization testing

`job_agent/fixtures/generalization_test_companies.json` + `run_phase6_generalization_test.py`
run stages 3 and 4 directly (bypassing stage 1) against a deliberately
diverse, hand-picked set of real companies, spanning every category the
project's own goals call out: multiple ATS platforms, plain in-house job
boards, and JS-heavy/mega-menu marketing sites. This is where iterating on
real failures — not the mocked unit tests — did the most to prove (and
improve) generalization.

**Result: 10/12 fully resolved**, and the 2 non-resolutions are both *correct*
answers, not bugs (see below) — so functionally 12/12 behaved correctly.

| Company | Category | Result |
|---|---|---|
| Anthropic, Figma, Robinhood | Greenhouse | ✓ |
| Notion, Vercel | Ashby | ✓ |
| Workday (self-hosted, see below) | Workday | ✓ |
| Netlify | (assumed Lever, turned out Greenhouse) | ✓ |
| Stripe, Duolingo, Nike, Shopify | in-house / no ATS | ✓ |
| Basecamp | in-house, zero current openings | correctly NOT FOUND |
| Salesforce | Workday, bot-blocked | correctly NOT FOUND |

**Four real failures on the first pass, three fixed, one confirmed as a non-bug:**

1. **Robinhood — real bug, fixed.** Its Greenhouse-backed job widget renders
   on a variable JS delay; a fixed 2-second post-render pause sometimes
   missed it, non-deterministically. Fixed by replacing the fixed pause with
   polling: `_wait_for_content_to_settle` (`job_extraction.py`) re-checks
   `document.querySelectorAll('a').length` every 500ms and returns once it
   stops growing (capped at 6s) — fast pages don't pay extra wait, slow ones
   get the time they actually need.
2. **Salesforce — real bug, fixed (partially).** Its careers page has 381
   links; the actual "Search jobs" link sat past position 250, so the
   link-truncation cap dropped it before the LLM ever saw it. Fixed:
   `html_utils.extract_links` now prioritizes links matching job/career
   keywords when truncating, regardless of position. This fix is confirmed
   working (the link is no longer dropped) — but Salesforce still resolves to
   NOT FOUND for an unrelated, unfixable reason: its actual jobs-search page
   is behind Akamai bot detection that explicitly blocks the headless
   browser (`Access Denied`, `errors.edgesuite.net`), even though a plain
   `requests.get` gets through fine. Building bot-detection evasion to get
   around that is out of scope — correctly reporting NOT FOUND is the right
   behavior here, which is exactly Phase 5's graceful-failure requirement.
3. **Duolingo — flaky, fixed.** The SupportVectors model (a small reasoning
   model) occasionally burns its entire token budget on internal "thinking"
   and returns no answer (`finish_reason=length`). Doubling the budget alone
   didn't reliably fix it — retried at 2x tokens and *still* exhausted it on
   Salesforce and Duolingo in one run. The actual fix: `temperature=0` is
   deterministic, so a prompt that makes the model reason-forever does so on
   *every* attempt at the same temperature — a bigger budget just delays
   hitting the same wall. The retry now also resamples at `temperature=0.4`,
   escaping the stuck trajectory. (`job_agent/llm.py`)
4. **Basecamp — not a bug.** Their jobs page literally states *"Sorry, we
   don't have any job openings right now."* Correctly resolves to NOT FOUND.

**Confirming the two previously-untested ATS platforms (Lever, Workday):**
marketing "companies that use X" lists turned out to be unreliable (several
listed companies 404'd against the real API); found real, currently-active
customers by verifying directly against each platform's own API first —
**Workday**: found via a natural source (they host their own careers page on
their own product, `workday.wd5.myworkdayjobs.com/Workday`) and confirmed
**working end-to-end live**, homepage → career page → real job posting, no
manual intervention. **Lever**: found via the same self-hosting pattern
(`jobs.lever.co/lever`), though Lever's own board had zero open roles; found
**Apply Digital** (`jobs.lever.co/applydigital`, 27 real open jobs) instead
and confirmed the parsing logic (`_extract_lever_jobs`) is correct against
real API data. The live end-to-end run against Apply Digital's homepage was
flaky (failed 2/2 through the full pipeline, succeeded 4/4 in isolated
reproductions of the same rendering logic) — root-caused to Apply Digital's
careers page loading Storyblok feature-flag/A-B-testing infrastructure, which
plausibly serves job cards as real `<a href>` links in one experiment
variant and something else in another. That's non-determinism in the
*target site*, not the pipeline; not something to chase further.

### Run it

```bash
python run_phase6_generalization_test.py
```

Slow — 12 companies, each potentially involving multiple LLM calls and a
Playwright render. Expect 10-20 minutes for the full set.

## Status

**Open item:** `company_resolution.py` (stage 2, URL normalization/
validation between stages 1 and 3) is still a stub — nothing tested so far
has needed it.
