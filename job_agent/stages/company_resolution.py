"""Stage 2: company resolution.

Normalizes and validates the (name, website) pairs LinkedIn ingestion produces
before career-page discovery is attempted on them: strip tracking params off the
URL, resolve redirects, drop unreachable domains. Not implemented yet — Phase 2
only covers stage 1 (LinkedIn ingestion).
"""

from job_agent.models import Company


def resolve(company: Company) -> Company:
    raise NotImplementedError("Stage 2 (company resolution) lands in a later phase.")
