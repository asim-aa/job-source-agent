"""Data types shared across the four pipeline stages."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Company:
    name: str
    website: str


@dataclass(frozen=True)
class CareerPage:
    company: Company
    url: str


@dataclass(frozen=True)
class JobPosting:
    career_page: CareerPage
    url: str


@dataclass(frozen=True)
class PipelineResult:
    """Final CSV row: company name, career page URL, open position URL."""

    company_name: str
    career_page_url: str
    job_url: str

    def to_csv_row(self) -> str:
        return f"{self.company_name},{self.career_page_url},{self.job_url}"
