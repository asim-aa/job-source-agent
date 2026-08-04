from job_agent.models import Company
from job_agent.stages.linkedin_ingestion import MockLinkedInProvider, get_provider


def test_fetch_companies_dedupes_by_website():
    provider = MockLinkedInProvider()
    companies = provider.fetch_companies()

    names = [c.name for c in companies]
    assert len(names) == len(set(names)), "expected no duplicate companies"
    assert Company(name="Ramp", website="https://ramp.com") in companies


def test_fetch_companies_respects_limit():
    provider = MockLinkedInProvider()
    companies = provider.fetch_companies(limit=3)
    assert len(companies) == 3


def test_fetch_companies_filters_by_query():
    provider = MockLinkedInProvider()
    companies = provider.fetch_companies(query="Design")
    assert companies == [Company(name="Figma", website="https://www.figma.com")]


def test_get_provider_unknown_name_raises():
    try:
        get_provider("proxycurl")
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass
