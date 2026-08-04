"""Stage 3: career page discovery.

Given a company website, finds its careers/jobs page. Plan (see README "Web agent
stack"): try a heuristic first (crawl the homepage, look for nav links matching
careers|jobs|join-us style text/href), and fall back to an LLM-driven browser
agent (Playwright + Claude deciding which link to follow) when the heuristic
finds nothing. Not implemented yet.
"""

from job_agent.models import CareerPage, Company


def discover(company: Company) -> CareerPage:
    raise NotImplementedError(
        "Stage 3 (career page discovery) lands in a later phase."
    )
