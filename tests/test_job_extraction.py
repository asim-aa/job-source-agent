from unittest.mock import Mock, patch

from job_agent.models import CareerPage, Company, JobPosting
from job_agent.stages import job_extraction as je

COMPANY = Company(name="Acme", website="https://acme.example")
CAREER_PAGE = CareerPage(company=COMPANY, url="https://acme.example/careers")


def test_extract_greenhouse_jobs_parses_response():
    fake_response = Mock()
    fake_response.raise_for_status = Mock()
    fake_response.json.return_value = {
        "jobs": [{"absolute_url": "https://boards.greenhouse.io/acme/jobs/123"}]
    }
    with patch.object(je.requests, "get", return_value=fake_response):
        assert je._extract_greenhouse_jobs("acme") == [
            "https://boards.greenhouse.io/acme/jobs/123"
        ]


def test_try_ats_dispatches_to_greenhouse_extractor():
    with patch.object(je, "_extract_greenhouse_jobs", return_value=["https://x/1"]) as mock_extract:
        result = je._try_ats("https://boards.greenhouse.io/acme")
    mock_extract.assert_called_once_with("acme")
    assert result == ["https://x/1"]


def test_try_ats_dispatches_to_greenhouse_embed_url():
    with patch.object(je, "_extract_greenhouse_jobs", return_value=["https://x/1"]) as mock_extract:
        result = je._try_ats("https://boards.greenhouse.io/embed/job_board?for=acme&b=embed")
    mock_extract.assert_called_once_with("acme")
    assert result == ["https://x/1"]


def test_try_ats_dispatches_to_lever_extractor():
    with patch.object(je, "_extract_lever_jobs", return_value=["https://x/1"]) as mock_extract:
        result = je._try_ats("https://jobs.lever.co/acme")
    mock_extract.assert_called_once_with("acme")
    assert result == ["https://x/1"]


def test_try_ats_dispatches_to_ashby_extractor():
    with patch.object(je, "_extract_ashby_jobs", return_value=["https://x/1"]) as mock_extract:
        result = je._try_ats("https://jobs.ashbyhq.com/acme")
    mock_extract.assert_called_once_with("acme")
    assert result == ["https://x/1"]


def test_try_ats_dispatches_to_workday_extractor():
    with patch.object(je, "_extract_workday_jobs", return_value=["https://x/1"]) as mock_extract:
        result = je._try_ats("https://acme.wd1.myworkdayjobs.com/en-US/External")
    mock_extract.assert_called_once()
    assert result == ["https://x/1"]


def test_try_ats_returns_empty_for_non_ats_url():
    assert je._try_ats("https://acme.example/careers") == []


def test_find_ats_iframe_returns_src_for_known_domain():
    html = (
        '<html><body><iframe src="https://boards.greenhouse.io/embed/job_board?'
        'for=acme"></iframe></body></html>'
    )
    assert je._find_ats_iframe(html, "https://acme.example/careers") == (
        "https://boards.greenhouse.io/embed/job_board?for=acme"
    )


def test_find_ats_iframe_returns_none_when_no_match():
    html = '<html><body><iframe src="https://youtube.com/embed/xyz"></iframe></body></html>'
    assert je._find_ats_iframe(html, "https://acme.example/careers") is None


def test_find_ats_link_returns_first_matching_url():
    links = [("About", "https://acme.example/about"), ("Apply", "https://jobs.lever.co/acme")]
    assert je._find_ats_link(links) == "https://jobs.lever.co/acme"


def test_find_ats_link_returns_none_when_no_match():
    links = [("About", "https://acme.example/about")]
    assert je._find_ats_link(links) is None


def test_classify_job_link_rejects_hallucinated_job_url():
    links = [("Software Engineer", "https://acme.example/careers/swe")]
    with patch.object(je, "call_llm", return_value="JOB: https://not-a-candidate.example"):
        assert je._classify_job_link(links, CAREER_PAGE.url, "Acme") is None


def test_classify_job_link_accepts_job_match():
    links = [("Software Engineer", "https://acme.example/careers/swe")]
    with patch.object(je, "call_llm", return_value="JOB: https://acme.example/careers/swe"):
        assert je._classify_job_link(links, CAREER_PAGE.url, "Acme") == (
            "job",
            "https://acme.example/careers/swe",
        )


def test_classify_job_link_accepts_listing_match():
    links = [("Explore open roles", "https://acme.example/careers/jobs")]
    with patch.object(je, "call_llm", return_value="LISTING: https://acme.example/careers/jobs"):
        assert je._classify_job_link(links, CAREER_PAGE.url, "Acme") == (
            "listing",
            "https://acme.example/careers/jobs",
        )


def test_classify_job_link_rejects_listing_pointing_at_itself():
    links = [("Careers", CAREER_PAGE.url)]
    with patch.object(je, "call_llm", return_value=f"LISTING: {CAREER_PAGE.url}"):
        assert je._classify_job_link(links, CAREER_PAGE.url, "Acme") is None


def test_classify_job_link_handles_none_response():
    links = [("Careers", "https://acme.example/careers/jobs")]
    with patch.object(je, "call_llm", return_value="NONE"):
        assert je._classify_job_link(links, CAREER_PAGE.url, "Acme") is None


def test_extract_one_uses_ats_shortcut_without_fetching_html():
    with patch.object(
        je, "_try_ats", return_value=["https://acme.example/careers/swe"]
    ) as mock_ats, patch.object(je, "_fetch") as mock_fetch:
        result = je.extract_one(CAREER_PAGE)

    assert result == JobPosting(career_page=CAREER_PAGE, url="https://acme.example/careers/swe")
    mock_ats.assert_called_once_with(CAREER_PAGE.url)
    mock_fetch.assert_not_called()


def test_extract_one_uses_ats_anchor_link_without_calling_llm():
    html = "<html><body><a href='https://jobs.lever.co/acme'>Apply</a></body></html>"
    with patch.object(je, "_try_ats") as mock_try_ats, patch.object(
        je, "_fetch", return_value=html
    ), patch.object(je, "call_llm") as mock_llm:
        mock_try_ats.side_effect = [[], ["https://jobs.lever.co/acme/123"]]
        result = je.extract_one(CAREER_PAGE)

    assert result == JobPosting(career_page=CAREER_PAGE, url="https://jobs.lever.co/acme/123")
    mock_llm.assert_not_called()


def test_extract_one_falls_back_to_static_html_classification():
    html = "<html><body><a href='/careers/swe'>Software Engineer</a></body></html>"
    with patch.object(je, "_try_ats", return_value=[]), patch.object(
        je, "_fetch", return_value=html
    ), patch.object(
        je, "call_llm", return_value="JOB: https://acme.example/careers/swe"
    ), patch.object(je, "_render_with_playwright") as mock_render:
        result = je.extract_one(CAREER_PAGE)

    assert result == JobPosting(career_page=CAREER_PAGE, url="https://acme.example/careers/swe")
    mock_render.assert_not_called()


def test_extract_one_follows_listing_link_one_hop():
    landing_html = "<html><body><a href='/careers/jobs'>Explore open roles</a></body></html>"
    listing_html = "<html><body><a href='/careers/jobs/swe'>Software Engineer</a></body></html>"

    def fake_fetch(url):
        if url == CAREER_PAGE.url:
            return landing_html
        if url == "https://acme.example/careers/jobs":
            return listing_html
        return None

    with patch.object(je, "_try_ats", return_value=[]), patch.object(
        je, "_fetch", side_effect=fake_fetch
    ), patch.object(
        je,
        "call_llm",
        side_effect=[
            "LISTING: https://acme.example/careers/jobs",
            "JOB: https://acme.example/careers/jobs/swe",
        ],
    ):
        result = je.extract_one(CAREER_PAGE)

    assert result == JobPosting(
        career_page=CAREER_PAGE, url="https://acme.example/careers/jobs/swe"
    )


def test_extract_one_falls_back_to_playwright_when_static_fails():
    no_jobs_html = "<html><body><a href='/about'>About</a></body></html>"
    rendered_html = "<html><body><a href='/careers/swe'>Software Engineer</a></body></html>"
    with patch.object(je, "_try_ats", return_value=[]), patch.object(
        je, "_fetch", return_value=no_jobs_html
    ), patch.object(
        je, "_render_with_playwright", return_value=rendered_html
    ), patch.object(
        je, "call_llm", side_effect=["NONE", "JOB: https://acme.example/careers/swe"]
    ):
        result = je.extract_one(CAREER_PAGE)

    assert result == JobPosting(career_page=CAREER_PAGE, url="https://acme.example/careers/swe")


def test_extract_one_returns_none_when_everything_fails():
    with patch.object(je, "_try_ats", return_value=[]), patch.object(
        je, "_fetch", return_value=None
    ), patch.object(je, "_render_with_playwright", return_value=None):
        assert je.extract_one(CAREER_PAGE) is None
