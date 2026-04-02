"""
Legacy script: Ozon FBO/FBS Sales Report Downloader
Source: old PC (\\home-pc\c\FBS FBO sell\ozon_reports.py)
Discovered: 2026-03-25 during old PC audit

What it does:
- Creates a report task via Ozon Seller API (/v1/report/postings/create)
- Polls task status until "success"
- Returns download link for the report

NOTE: Original had hardcoded CLIENT_ID and API_KEY — removed here.
      Load credentials from environment variables instead.

Relevant for: future Ozon FBO/FBS worker (not yet planned in Roadmap)
API docs: https://api-seller.ozon.ru/docs/#tag/Reports
"""

import os
import time
import requests

CLIENT_ID = os.environ["OZON_CLIENT_ID"]
API_KEY = os.environ["OZON_API_KEY"]

HEADERS = {
    "Client-Id": CLIENT_ID,
    "Api-Key": API_KEY,
    "Content-Type": "application/json",
}


def create_postings_report(date_from: str, date_to: str, report_type: str = "ALL") -> str:
    """
    Create a postings report task.
    report_type: "ALL" | "FBO" | "FBS"
    Returns task_id.
    """
    url = "https://api-seller.ozon.ru/v1/report/postings/create"
    payload = {
        "date_from": date_from,
        "date_to": date_to,
        "report_type": report_type,
    }
    r = requests.post(url, headers=HEADERS, json=payload)
    r.raise_for_status()
    task_id = r.json()["result"]["task_id"]
    print(f"Report task created: {task_id}")
    return task_id


def wait_for_report(task_id: str, poll_interval: int = 5) -> str:
    """
    Poll report status until success. Returns download URL.
    """
    status_url = "https://api-seller.ozon.ru/v1/report/info"
    while True:
        resp = requests.post(status_url, headers=HEADERS, json={"task_id": task_id})
        resp.raise_for_status()
        result = resp.json()["result"]
        status = result["status"]
        if status == "success":
            link = result["file"]
            print(f"Report ready: {link}")
            return link
        elif status == "failed":
            raise RuntimeError(f"Report generation failed for task_id={task_id}")
        print(f"Status: {status}, waiting {poll_interval}s...")
        time.sleep(poll_interval)


if __name__ == "__main__":
    task_id = create_postings_report(
        date_from="2024-01-01T00:00:00",
        date_to="2024-12-31T23:59:59",
        report_type="ALL",
    )
    download_url = wait_for_report(task_id)
    print(f"Download: {download_url}")
