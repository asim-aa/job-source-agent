#!/usr/bin/env python3
"""Phase 2 deliverable: run LinkedIn ingestion and print {company_name, company_website} pairs.

Usage:
    python run_phase2_demo.py
    python run_phase2_demo.py --query "software engineer" --limit 5
"""

import argparse

from job_agent.config import LINKEDIN_PROVIDER
from job_agent.pipeline import ingest_companies
from job_agent.stages.linkedin_ingestion import get_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2: LinkedIn ingestion demo")
    parser.add_argument("--query", default="", help="Filter listings by job title substring")
    parser.add_argument("--limit", type=int, default=50, help="Max companies to return")
    args = parser.parse_args()

    provider = get_provider(LINKEDIN_PROVIDER)
    companies = ingest_companies(provider, query=args.query, limit=args.limit)

    print(f"{'company_name':<20} company_website")
    for company in companies:
        print(f"{company.name:<20} {company.website}")


if __name__ == "__main__":
    main()
