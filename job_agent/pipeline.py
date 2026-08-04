"""Sequential orchestration: stage 1 -> stage 3 -> stage 4.

A plain function, not an agent framework — the "agent" behavior (an LLM
deciding which link to follow) lives inside stages 3 and 4, not in how stages
are chained together.

Stage 2 (company resolution) is still a stub, so this currently goes straight
from LinkedIn ingestion to career page discovery on the raw (name, website)
LinkedIn returned.

Phase 5: failures at any per-company step (no career page found, no open
position found) are logged and that company is dropped from the results — one
bad company must not stop the run for the rest, since "generic across
different site formats" guarantees some sites won't cooperate.
"""

from __future__ import annotations

from job_agent.models import Company, PipelineResult
from job_agent.stages.career_page_discovery import discover
from job_agent.stages.job_extraction import extract_one
from job_agent.stages.linkedin_ingestion import LinkedInProvider


def ingest_companies(
    provider: LinkedInProvider, query: str = "", limit: int = 50
) -> list[Company]:
    return provider.fetch_companies(query=query, limit=limit)


def run_pipeline(
    provider: LinkedInProvider, query: str = "", limit: int = 50
) -> list[PipelineResult]:
    companies = ingest_companies(provider, query=query, limit=limit)
    results: list[PipelineResult] = []

    for company in companies:
        career_page = discover(company)
        if career_page is None:
            print(f"SKIP: no career page found for {company.name} — dropping from results.")
            continue

        job_posting = extract_one(career_page)
        if job_posting is None:
            print(f"SKIP: no open position found for {company.name} — dropping from results.")
            continue

        results.append(
            PipelineResult(
                company_name=company.name,
                career_page_url=career_page.url,
                job_url=job_posting.url,
            )
        )

    return results
