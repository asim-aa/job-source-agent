"""Phase 5: normalize pipeline results into the required
(company_name, career_page_url, job_url) tuple and write them to CSV."""

from __future__ import annotations

import csv
from pathlib import Path

from job_agent.models import PipelineResult

CSV_HEADER = ["company_name", "career_page_url", "job_url"]


def write_csv(results: list[PipelineResult], path: Path) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for r in results:
            writer.writerow([r.company_name, r.career_page_url, r.job_url])
