#!/usr/bin/env python3
"""Phase 6: generalization testing.

Runs stages 3 (career page discovery) and 4 (job extraction) directly against
a deliberately diverse, hand-picked set of real companies —
job_agent/fixtures/generalization_test_companies.json — bypassing stage 1
(LinkedIn ingestion), since this phase is about testing generalization across
site structures, not the ingestion step. The set spans: ATS platforms
(Greenhouse, Lever, Ashby, Workday), plain in-house job boards, and
JS-heavy/mega-menu marketing sites.

Makes real network requests and real LLM calls. Slow (Playwright renders and
multiple LLM calls per company) — expect several minutes for the full set.

Usage:
    python run_phase6_generalization_test.py
"""

import json
import time
from pathlib import Path

from job_agent.models import Company
from job_agent.stages.career_page_discovery import discover
from job_agent.stages.job_extraction import extract_one

FIXTURE_PATH = Path(__file__).parent / "job_agent" / "fixtures" / "generalization_test_companies.json"


def main() -> None:
    companies_data = json.loads(FIXTURE_PATH.read_text())

    results = []
    for entry in companies_data:
        company = Company(name=entry["name"], website=entry["website"])
        print(f"\n=== {company.name} ({entry['note']}) ===")

        t0 = time.time()
        career_page = discover(company)
        if career_page is None:
            elapsed = time.time() - t0
            print(f"  career page: NOT FOUND ({elapsed:.1f}s)")
            results.append((company.name, "NOT FOUND", "-", elapsed))
            continue
        print(f"  career page: {career_page.url}")

        job_posting = extract_one(career_page)
        elapsed = time.time() - t0
        job_url = job_posting.url if job_posting else "NOT FOUND"
        print(f"  job url: {job_url} ({elapsed:.1f}s)")
        results.append((company.name, career_page.url, job_url, elapsed))

    print("\n" + "=" * 100)
    print(f"{'company':<15} {'career_page':<45} {'job_url':<60}")
    print("=" * 100)
    passed = 0
    for name, career_url, job_url, elapsed in results:
        ok = career_url != "NOT FOUND" and job_url != "NOT FOUND"
        passed += ok
        print(f"{name:<15} {career_url:<45} {job_url:<60} ({elapsed:.1f}s)")

    print(f"\n{passed}/{len(results)} companies fully resolved (career page + job URL)")


if __name__ == "__main__":
    main()
