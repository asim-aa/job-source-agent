#!/usr/bin/env python3
"""Phase 4 deliverable: LinkedIn ingestion (stage 1) -> career page discovery
(stage 3) -> open position extraction (stage 4), skipping stage 2 (company
resolution) since it isn't built yet.

Makes real network requests (company homepages, career pages, ATS APIs,
optionally a headless-browser render) and real LLM calls — needs a working
LLM_PROVIDER config in .env (see .env.example), and `playwright install
chromium` run once if the JS-rendered fallback is needed.

Usage:
    python run_phase4_demo.py
    python run_phase4_demo.py --query "engineer" --limit 3
"""

import argparse

from job_agent.config import LINKEDIN_PROVIDER
from job_agent.pipeline import ingest_companies
from job_agent.stages.career_page_discovery import discover
from job_agent.stages.job_extraction import extract_one
from job_agent.stages.linkedin_ingestion import get_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4: job URL extraction demo")
    parser.add_argument("--query", default="", help="Filter listings by job title substring")
    parser.add_argument("--limit", type=int, default=5, help="Max companies to process")
    args = parser.parse_args()

    provider = get_provider(LINKEDIN_PROVIDER)
    companies = ingest_companies(provider, query=args.query, limit=args.limit)

    print(f"{'company_name':<20} {'career_page_url':<40} job_url")
    for company in companies:
        career_page = discover(company)
        if career_page is None:
            print(f"{company.name:<20} {'NOT FOUND':<40}")
            continue

        job_posting = extract_one(career_page)
        job_url = job_posting.url if job_posting else "NOT FOUND"
        print(f"{company.name:<20} {career_page.url:<40} {job_url}")


if __name__ == "__main__":
    main()
