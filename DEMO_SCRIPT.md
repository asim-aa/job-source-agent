# Demo video script

Verified live and working as of this writing — [/tmp/demo_verify.csv](/tmp/demo_verify.csv)
has the exact run this script is based on. Re-run `python run_pipeline.py --limit 5`
once right before recording (not during) so you know it's still fresh.

## 1. Open (30s) — state the problem this solves

Say something like:

> "LinkedIn job postings are a good *signal* that a company is hiring, but the
> listing itself is often stale, aggregated, or missing by the time you see it.
> This pipeline uses LinkedIn as that signal, but instead of trusting LinkedIn's
> own listing, it navigates directly to the company's own career site and pulls
> out one real, currently-open position — a more direct, more reliable path to
> an actual applyable job."

This directly answers the brief's framing: *"Use LinkedIn as the hiring
signal, but build a more direct way with the company's career page directly
to exact new open jobs."* Say that reasoning out loud — it's the whole point.

## 2. Architecture (30-45s) — four stages, show the README pipeline list

Pull up [README.md](README.md) and point at the 4 stages:
1. LinkedIn ingestion → company name + website
2. Career page discovery → the company's actual careers page
3. Job extraction → one specific open position URL
4. Output → `company_name, career_page_url, job_url`

One line on genericness: *"Stages 2 and 3 use an LLM to read each page like a
person would — click the link that looks like 'Careers', then click the link
that looks like an actual job — rather than hardcoded selectors per company,
which is what makes it generalize across different site layouts instead of
breaking on the first company with a different HTML structure."*

## 3. Live run (2-3 min) — the actual proof

```bash
cd job-source-agent
source .venv/bin/activate
python run_pipeline.py --limit 5
```

While it runs (takes a couple minutes — real network + LLM calls, not
canned), narrate what's happening: it's fetching each company's real
homepage, an LLM is picking out the careers link, then doing the same thing
again to find one real job posting.

**When the output lands, point at the diversity across these 5** — this is
your generic-across-formats evidence, live:
- **Anthropic, Figma** → resolved via Greenhouse's public API (an ATS platform)
- **Notion** → resolved via Ashby (a different ATS platform)
- **Duolingo** → resolved via their own in-house `/jobs` page, no ATS at all
- **Stripe** → their careers page doesn't list jobs directly — the pipeline
  followed one more link ("browse open roles") to find the actual posting,
  showing it adapts when a site needs an extra hop

Four different site architectures, same command, no per-company code.

## 4. Show the output file (15s)

```bash
cat results.csv
```

This is the exact required format: `company_name, career_page_url, job_url`.

## 5. Close (30s) — broader evidence + one honest scope note

Mention (doesn't need to be on-screen, just say it): *"Beyond these 5, this
was tested against 12 companies deliberately chosen to span every category —
multiple ATS platforms, in-house boards, and JS-heavy marketing sites like
Nike and Shopify — and correctly resolved or correctly reported 'not found'
on all 12."* (See `run_phase6_generalization_test.py` / README Phase 6 if you
want the receipts on screen.)

One honest scope note, said plainly and confidently, not apologetically:
*"The LinkedIn ingestion step reads from a small local dataset rather than a
live paid scraping API for this demo — that's a one-file swap
(`LinkedInProvider`), the interface is already built for it. The harder
engineering — reading an arbitrary company site and finding a real job
posting generically — is what's actually live here."*

## Tips

- Rehearse once, silently, right before recording — confirms nothing drifted
  and gets your timing down.
- If a company happens to fail live on camera (websites change), that's fine
  to leave in — briefly note "and this one didn't find a match, which the
  pipeline handles by skipping it rather than crashing" — that's Phase 5's
  graceful-failure behavior working as designed, not a flaw to hide.
- Total runtime for `--limit 5` is usually 1-3 minutes. Don't pad the video
  waiting on it in real time if you don't want to — a quick "fast-forward
  through the wait, here's the result" cut is normal for this kind of demo.
