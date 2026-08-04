from job_agent.models import PipelineResult
from job_agent.output import write_csv


def test_write_csv_writes_header_and_rows(tmp_path):
    results = [
        PipelineResult(
            company_name="Acme",
            career_page_url="https://acme.example/careers",
            job_url="https://acme.example/careers/swe",
        ),
    ]
    out_path = tmp_path / "results.csv"
    write_csv(results, out_path)

    lines = out_path.read_text().splitlines()
    assert lines[0] == "company_name,career_page_url,job_url"
    assert lines[1] == "Acme,https://acme.example/careers,https://acme.example/careers/swe"
