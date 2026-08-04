from unittest.mock import patch

from job_agent.models import CareerPage, Company
from job_agent.stages import career_page_discovery as cpd

HOMEPAGE_HTML = """
<html><body>
<nav>
  <a href="/product">Product</a>
  <a href="/careers">Careers</a>
  <a href="mailto:hi@acme.com">Email us</a>
  <a href="#top">Back to top</a>
  <a href="/careers">Careers</a>
</nav>
</body></html>
"""

COMPANY = Company(name="Acme", website="https://acme.example")


def test_extract_links_dedupes_and_filters_non_http_links():
    links = cpd._extract_links(HOMEPAGE_HTML, COMPANY.website)
    assert links == [
        ("Product", "https://acme.example/product"),
        ("Careers", "https://acme.example/careers"),
    ]


def test_classify_homepage_links_accepts_exact_match():
    links = [("Careers", "https://acme.example/careers")]
    with patch.object(cpd, "call_llm", return_value="https://acme.example/careers"):
        assert cpd._classify_homepage_links(links, "Acme") == "https://acme.example/careers"


def test_classify_homepage_links_rejects_hallucinated_url():
    links = [("Careers", "https://acme.example/careers")]
    with patch.object(cpd, "call_llm", return_value="https://not-a-real-candidate.example"):
        assert cpd._classify_homepage_links(links, "Acme") is None


def test_classify_homepage_links_handles_none_response():
    links = [("Careers", "https://acme.example/careers")]
    with patch.object(cpd, "call_llm", return_value="NONE"):
        assert cpd._classify_homepage_links(links, "Acme") is None


def test_discover_returns_homepage_match_without_touching_fallbacks():
    with patch.object(cpd, "_fetch", return_value=HOMEPAGE_HTML) as mock_fetch, patch.object(
        cpd, "call_llm", return_value="https://acme.example/careers"
    ), patch.object(cpd, "_guess_common_paths") as mock_guess, patch.object(
        cpd, "_search_fallback"
    ) as mock_search:
        result = cpd.discover(COMPANY)

    assert result == CareerPage(company=COMPANY, url="https://acme.example/careers")
    mock_fetch.assert_called_once_with(COMPANY.website)
    mock_guess.assert_not_called()
    mock_search.assert_not_called()


def test_discover_falls_back_to_path_guess_when_homepage_has_no_match():
    no_careers_html = "<html><body><a href='/product'>Product</a></body></html>"

    def fake_fetch(url):
        if url == COMPANY.website:
            return no_careers_html
        if url == "https://acme.example/careers":
            return "<html><title>Careers at Acme</title><body>Open roles</body></html>"
        return None

    with patch.object(cpd, "_fetch", side_effect=fake_fetch), patch.object(
        cpd, "call_llm", side_effect=["NONE", "YES"]
    ), patch.object(cpd, "_search_fallback") as mock_search:
        result = cpd.discover(COMPANY)

    assert result == CareerPage(company=COMPANY, url="https://acme.example/careers")
    mock_search.assert_not_called()


def test_discover_returns_none_when_everything_fails():
    with patch.object(cpd, "_fetch", return_value=None), patch.object(
        cpd, "_search_fallback", return_value=None
    ):
        assert cpd.discover(COMPANY) is None
