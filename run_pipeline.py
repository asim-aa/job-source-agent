#!/usr/bin/env python3
"""Phase 5 deliverable: full pipeline, stage 1 -> stage 3 -> stage 4, emitting
the required (company_name, career_page_url, job_url) rows as CSV.

Makes real network requests (company homepages, career pages, ATS APIs,
optionally a headless-browser render) and real LLM calls — needs a working
LLM_PROVIDER config in .env (see .env.example).

Usage:
    python run_pipeline.py
    python run_pipeline.py --query "engineer" --limit 3 --out results.csv
"""

import argparse
from pathlib import Path

from job_agent.config import LINKEDIN_PROVIDER
from job_agent.output import write_csv
from job_agent.pipeline import run_pipeline
from job_agent.stages.linkedin_ingestion import get_provider


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5: full pipeline demo")
    parser.add_argument("--query", default="", help="Filter listings by job title substring")
    parser.add_argument("--limit", type=int, default=5, help="Max companies to process")
    parser.add_argument("--out", default="results.csv", help="Output CSV path")
    args = parser.parse_args()

    provider = get_provider(LINKEDIN_PROVIDER)
    results = run_pipeline(provider, query=args.query, limit=args.limit)

    print()
    print(f"{'company_name':<20} {'career_page_url':<40} job_url")
    for r in results:
        print(f"{r.company_name:<20} {r.career_page_url:<40} {r.job_url}")

    out_path = Path(args.out)
    write_csv(results, out_path)
    print(f"\nWrote {len(results)} rows to {out_path}")


if __name__ == "__main__":
    main()
