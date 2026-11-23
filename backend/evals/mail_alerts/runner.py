"""The ``mail_alerts`` eval: how well the six fixed readers take jobs out of alert emails (T046).

No AI is asked. Each synthetic email in ``tests/fixtures/mail`` goes through the real pieces (MIME
flattening, the sender's site, the site's reader) and is scored against ``expected.yaml``
(SC-002, readers part). A job counts as taken out only with its title, company and link all
right. A value the email's text does not hold, or a job the email does not list, is invented.
An email whose reader finds nothing is left to the AI. The report holds counts only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import yaml

from hiretitan.mail.domain.alerts import AlertJob
from hiretitan.mail.domain.mime import flatten_message
from hiretitan.mail.domain.readers import READERS, read_alert
from hiretitan.mail.domain.senders import site_for_address

FIXTURES: Final = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "mail"
JOB_RECALL_MIN: Final = 0.95
READ_WITHOUT_AI_MIN: Final = 0.90


@dataclass(frozen=True, slots=True)
class EmailScore:
    expected: int
    correct: int  # title, company and link all right
    titles: int
    companies: int
    links: int
    invented: int
    read_without_ai: bool


@dataclass(frozen=True, slots=True)
class SiteReport:
    site: str
    emails: int
    jobs: int
    correct: int
    titles: int
    companies: int
    links: int
    invented: int
    read_without_ai: int

    @property
    def recall(self) -> float:
        return self.correct / self.jobs if self.jobs else 1.0


@dataclass(frozen=True, slots=True)
class MailAlertsReport:
    sites: list[SiteReport]
    unknown_layouts: int  # emails from no built-in site: always the AI's

    @property
    def emails(self) -> int:
        return sum(s.emails for s in self.sites)

    @property
    def job_recall(self) -> float:
        jobs = sum(s.jobs for s in self.sites)
        return sum(s.correct for s in self.sites) / jobs if jobs else 1.0

    @property
    def invented(self) -> int:
        return sum(s.invented for s in self.sites)

    @property
    def read_without_ai(self) -> float:
        return sum(s.read_without_ai for s in self.sites) / self.emails if self.emails else 1.0

    @property
    def passes(self) -> bool:
        return (
            self.job_recall >= JOB_RECALL_MIN
            and self.invented == 0
            and self.read_without_ai >= READ_WITHOUT_AI_MIN
        )


def score_email(
    wanted: Sequence[Mapping[str, Any]], found: Sequence[AlertJob], email_text: str
) -> EmailScore:
    by_link = {w["link"]: w for w in wanted}
    titles = companies = links = correct = invented = 0
    for job in found:
        values = (job.title, job.company, job.location)
        invented += sum(1 for v in values if v is not None and v not in email_text)
        match = by_link.get(job.link)
        if match is None:
            invented += 1  # a job the email does not list
            continue
        links += 1
        title_ok, company_ok = job.title == match["title"], job.company == match["company"]
        titles += title_ok
        companies += company_ok
        correct += title_ok and company_ok
    return EmailScore(
        expected=len(wanted),
        correct=correct,
        titles=titles,
        companies=companies,
        links=links,
        invented=invented,
        read_without_ai=bool(found),
    )


def evaluate(fixtures: Path = FIXTURES) -> MailAlertsReport:
    emails = yaml.safe_load((fixtures / "expected.yaml").read_text("utf-8"))["emails"]
    scores: dict[str, list[EmailScore]] = {site: [] for site in READERS}
    unknown = 0
    for name, entry in sorted(emails.items()):
        site = site_for_address(entry["sender"], READERS)
        if site is None:
            unknown += 1
            continue
        flat = flatten_message((fixtures / "eml" / name).read_bytes())
        text = " ".join(line.text for line in flat.lines)
        found = read_alert(site, flat, datetime.fromisoformat(entry["received"]))
        scores[site].append(score_email(entry.get("jobs") or [], found, text))
    return MailAlertsReport(
        sites=[_site_report(site, s) for site, s in scores.items()], unknown_layouts=unknown
    )


def _site_report(site: str, scores: Sequence[EmailScore]) -> SiteReport:
    return SiteReport(
        site=site,
        emails=len(scores),
        jobs=sum(s.expected for s in scores),
        correct=sum(s.correct for s in scores),
        titles=sum(s.titles for s in scores),
        companies=sum(s.companies for s in scores),
        links=sum(s.links for s in scores),
        invented=sum(s.invented for s in scores),
        read_without_ai=sum(s.read_without_ai for s in scores),
    )


def _pct(value: float) -> str:
    return f"{value:.1%}"


def render_report(report: MailAlertsReport, *, day: str) -> str:
    verdict = "PASS" if report.passes else "FAIL"
    lines = [
        f"# mail_alerts eval, {day}: {verdict}",
        "",
        "The six fixed alert readers over the synthetic fixtures in `tests/fixtures/mail` (no AI).",
        "SC-002 targets: at least 95% of jobs with title, company and link right; 0 invented",
        "values; at least 90% of the built-in sites' emails read without the AI.",
        "",
        "| Site | Emails | Jobs | Correct | Title | Company | Link | Invented | Read without AI |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in report.sites:
        lines.append(
            f"| {s.site} | {s.emails} | {s.jobs} | {_pct(s.recall)} | {s.titles} | "
            f"{s.companies} | {s.links} | {s.invented} | {s.read_without_ai}/{s.emails} |"
        )
    lines += [
        "",
        f"- Emails from built-in sites: {report.emails}",
        f"- Jobs taken out correctly: {_pct(report.job_recall)} (target 95%)",
        f"- Invented values: {report.invented} (target 0)",
        f"- Read without the AI: {_pct(report.read_without_ai)} (target 90%)",
        f"- Emails in a layout no fixed reader knows (left to the AI): {report.unknown_layouts}",
        "",
        "The layouts are guesses until real alerts are checked (T005); the AI fallback is",
        "measured with the deferred evals, which need a key.",
        "",
    ]
    return "\n".join(lines)
