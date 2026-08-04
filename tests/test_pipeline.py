from unittest.mock import patch

from job_agent.models import CareerPage, JobPosting
from job_agent.pipeline import run_pipeline
from job_agent.stages.linkedin_ingestion import MockLinkedInProvider


def test_run_pipeline_skips_companies_with_no_career_page():
    provider = MockLinkedInProvider()

    def fake_discover(company):
        if company.name == "Anthropic":
            return None
        return CareerPage(company=company, url=f"{company.website}/careers")

    def fake_extract(career_page):
        return JobPosting(career_page=career_page, url=f"{career_page.url}/swe")

    with patch("job_agent.pipeline.discover", side_effect=fake_discover), patch(
        "job_agent.pipeline.extract_one", side_effect=fake_extract
    ):
        results = run_pipeline(provider, limit=3)

    names = [r.company_name for r in results]
    assert "Anthropic" not in names
    assert len(results) == 2


def test_run_pipeline_skips_companies_with_no_open_position():
    provider = MockLinkedInProvider()

    def fake_discover(company):
        return CareerPage(company=company, url=f"{company.website}/careers")

    with patch("job_agent.pipeline.discover", side_effect=fake_discover), patch(
        "job_agent.pipeline.extract_one", return_value=None
    ):
        results = run_pipeline(provider, limit=2)

    assert results == []


def test_run_pipeline_builds_correct_result_rows():
    provider = MockLinkedInProvider()

    def fake_discover(company):
        return CareerPage(company=company, url=f"{company.website}/careers")

    def fake_extract(career_page):
        return JobPosting(career_page=career_page, url=f"{career_page.url}/swe")

    with patch("job_agent.pipeline.discover", side_effect=fake_discover), patch(
        "job_agent.pipeline.extract_one", side_effect=fake_extract
    ):
        results = run_pipeline(provider, limit=1)

    assert len(results) == 1
    result = results[0]
    assert result.company_name == "Anthropic"
    assert result.career_page_url == "https://www.anthropic.com/careers"
    assert result.job_url == "https://www.anthropic.com/careers/swe"
