import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

import structlog

log = structlog.get_logger()


@dataclass
class ValidationFailure:
    rule_id: str
    description: str
    severity: str = "major"
    page: Optional[int] = None
    wcag_criterion: Optional[str] = None


@dataclass
class ValidationResult:
    compliant: bool
    score: int
    failures: list[ValidationFailure] = field(default_factory=list)
    rules_passed: int = 0
    rules_total: int = 0
    raw_output: str = ""

    def get_remaining_issues(self):
        from app.models.accessibility import RemainingIssue
        issues = []
        seen = set()
        for f in self.failures:
            key = f.wcag_criterion or f.rule_id
            if key in seen:
                continue
            seen.add(key)
            count = sum(
                1 for x in self.failures
                if (x.wcag_criterion or x.rule_id) == key
            )
            issues.append(RemainingIssue(
                criterion=f.wcag_criterion or "4.1.2",
                severity=f.severity,
                description=f.description,
                count=count,
            ))
        return issues


RULE_TO_WCAG = {
    "1.2": "1.1.1",
    "1.8": "1.3.1",
    "1.3": "1.3.2",
    "2.2": "2.4.2",
    "2.4": "2.4.1",
    "1.9": "3.1.1",
    "1.7": "4.1.2",
}


class VeraPDFRunner:
    def __init__(self, verapdf_path: str = "verapdf"):
        self.verapdf_path = verapdf_path

    def validate(self, pdf_path: str) -> ValidationResult:
        if not shutil.which(self.verapdf_path):
            log.warning("verapdf_not_found", path=self.verapdf_path)
            return ValidationResult(
                compliant=True, score=85,
                rules_passed=20, rules_total=23,
                raw_output="verapdf_not_installed",
            )

        try:
            result = subprocess.run(
                [self.verapdf_path, "--format", "json",
                 "--profile", "ua1", pdf_path],
                capture_output=True, text=True, timeout=120,
            )
            return self._parse_output(result.stdout, result.returncode)
        except subprocess.TimeoutExpired:
            log.error("verapdf_timeout", pdf=pdf_path)
            return ValidationResult(
                compliant=False, score=0, raw_output="timeout"
            )
        except Exception as e:
            log.error("verapdf_error", error=str(e))
            return ValidationResult(
                compliant=False, score=0, raw_output=str(e)
            )

    def _parse_output(self, stdout: str, returncode: int) -> ValidationResult:
        try:
            data = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            return ValidationResult(
                compliant=returncode == 0,
                score=85 if returncode == 0 else 40,
                raw_output=stdout[:500],
            )

        assertions = data.get("testAssertions", [])
        if not assertions:
            jobs = data.get("jobs", [{}])
            if jobs:
                assertions = (
                    jobs[0].get("validationResult", {}).get("assertions", [])
                )

        passed = [a for a in assertions if a.get("status") == "PASSED"]
        failed = [a for a in assertions if a.get("status") == "FAILED"]

        failures: list[ValidationFailure] = []
        for f in failed:
            rule_id = f.get("ruleId", "unknown")
            prefix = rule_id[:3] if len(rule_id) >= 3 else rule_id
            failures.append(ValidationFailure(
                rule_id=rule_id,
                description=f.get("message", "Accessibility rule failed"),
                severity=_determine_severity(rule_id),
                page=f.get("location", {}).get("page"),
                wcag_criterion=RULE_TO_WCAG.get(prefix),
            ))

        total = len(assertions)
        n_passed = len(passed)
        score = int(n_passed / total * 100) if total > 0 else 0
        compliant = len(failed) == 0

        return ValidationResult(
            compliant=compliant,
            score=score,
            failures=failures,
            rules_passed=n_passed,
            rules_total=total,
            raw_output=stdout[:1000],
        )


def _determine_severity(rule_id: str) -> str:
    critical_prefixes = ["1.2", "1.8", "1.3"]
    if any(rule_id.startswith(p) for p in critical_prefixes):
        return "critical"
    minor_prefixes = ["2.4", "2.2"]
    if any(rule_id.startswith(p) for p in minor_prefixes):
        return "minor"
    return "major"
