#!/usr/bin/env python3
"""Phase 3 deliverable: LinkedIn ingestion (stage 1) -> career page discovery
(stage 3), skipping stage 2 (company resolution) since it isn't built yet.

Makes real network requests to each company's homepage and real LLM calls
(cost: a handful of short prompts per company) — needs a working LLM_PROVIDER
config in .env (see .env.example).

Usage:
    python run_phase3_demo.py
    python run_phase3_demo.py --query "engineer" --limit 3
"""

import argparse

from job_agent.config import LINKEDIN_PROVIDER
from job_agent.pipeline import ingest_companies
from job_agent.stages.career_page_discovery import discover
from job_agent.stages.linkedin_ingestion import get_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3: career page discovery demo")
    parser.add_argument("--query", default="", help="Filter listings by job title substring")
    parser.add_argument("--limit", type=int, default=5, help="Max companies to process")
    args = parser.parse_args()

    provider = get_provider(LINKEDIN_PROVIDER)
    companies = ingest_companies(provider, query=args.query, limit=args.limit)

    print(f"{'company_name':<20} career_page_url")
    for company in companies:
        career_page = discover(company)
        url = career_page.url if career_page else "NOT FOUND"
        print(f"{company.name:<20} {url}")


if __name__ == "__main__":
    main()
