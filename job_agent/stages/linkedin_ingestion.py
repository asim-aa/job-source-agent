"""Stage 1: LinkedIn ingestion.

Crawls LinkedIn job listings and resolves each to a (company_name, company_website)
pair. Real providers (Proxycurl, Bright Data, RapidAPI, ...) all return listings in
roughly this shape, so `LinkedInProvider` is the seam: swapping the mock for a paid
API later means writing one class, not touching the rest of the pipeline.
"""

import json
from pathlib import Path
from typing import Protocol

from job_agent.models import Company

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class LinkedInProvider(Protocol):
    def fetch_companies(self, query: str = "", limit: int = 50) -> list[Company]:
        """Return deduplicated companies mentioned in matching job listings."""
        ...


class MockLinkedInProvider:
    """Reads canned job-listing data instead of calling a paid scraping API.

    Chosen over a real provider (Proxycurl/Bright Data) for this project to avoid
    per-call pricing and contract risk during development; swap in a real
    implementation of LinkedInProvider later without changing callers.
    """

    def __init__(self, fixture_path: Path | None = None):
        self.fixture_path = fixture_path or FIXTURES_DIR / "linkedin_job_listings.json"

    def fetch_companies(self, query: str = "", limit: int = 50) -> list[Company]:
        listings = json.loads(self.fixture_path.read_text())

        if query:
            query_lower = query.lower()
            listings = [
                listing
                for listing in listings
                if query_lower in listing["job_title"].lower()
            ]

        seen_websites: set[str] = set()
        companies: list[Company] = []
        for listing in listings:
            website = listing["company_website"]
            if website in seen_websites:
                continue
            seen_websites.add(website)
            companies.append(Company(name=listing["company_name"], website=website))
            if len(companies) >= limit:
                break

        return companies


def get_provider(name: str = "mock") -> LinkedInProvider:
    if name == "mock":
        return MockLinkedInProvider()
    raise NotImplementedError(
        f"LinkedIn provider '{name}' is not implemented yet. "
        "Implement LinkedInProvider and register it here."
    )
