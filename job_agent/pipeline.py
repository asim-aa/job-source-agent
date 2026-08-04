"""Sequential orchestration: stage 1 -> stage 2 -> stage 3 -> stage 4.

A plain function, not an agent framework — the "agent" behavior (an LLM deciding
which link to click) lives inside stage 3, not in how stages are chained together.

Currently only stage 1 is implemented, so run_pipeline stops there. As stages
2-4 land, extend this loop to call them per company.
"""

from job_agent.models import Company
from job_agent.stages.linkedin_ingestion import LinkedInProvider


def ingest_companies(
    provider: LinkedInProvider, query: str = "", limit: int = 50
) -> list[Company]:
    return provider.fetch_companies(query=query, limit=limit)
