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

**Web agent stack (stage 3, later phase):** heuristic first, LLM fallback.
Crawl the homepage, look for nav links whose text/href matches
`careers|jobs|join-us`-style patterns; only when that finds nothing, hand the
page to an LLM (Claude) driving Playwright to pick the right link. Heuristic-first
keeps the common case fast and free; the LLM fallback is what makes the pipeline
"generic across different site formats" per the project's stated goal, instead of
hand-tuning selectors per company.

**Stages 2-4 are stubbed** (`NotImplementedError` with a docstring) — this repo
currently implements Phase 1 (this scaffold) and Phase 2 (stage 1) only.

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

## Roadmap

- Phase 3: implement `company_resolution.py` (URL normalization/validation) and
  `career_page_discovery.py` (heuristic crawl + LLM/Playwright fallback)
- Phase 4: implement `job_extraction.py`, wire all four stages together in
  `pipeline.py`, emit the final CSV
- Phase 5: demo video showing the pipeline end-to-end against real company sites
