import json
from unittest.mock import patch, MagicMock

import pytest

from app.services.validation.verapdf_runner import (
    VeraPDFRunner, ValidationFailure, ValidationResult, _determine_severity, RULE_TO_WCAG
)


class TestDetermineSeverity:
    def test_critical_for_alt_text_rules(self):
        assert _determine_severity("1.2.1") == "critical"

    def test_critical_for_structure_rules(self):
        assert _determine_severity("1.3.1") == "critical"

    def test_minor_for_bookmark_rules(self):
        assert _determine_severity("2.4.1") == "minor"

    def test_major_default(self):
        assert _determine_severity("9.9.9") == "major"


class TestRuleToWcag:
    def test_maps_known_prefixes(self):
        assert RULE_TO_WCAG["1.2"] == "1.1.1"
        assert RULE_TO_WCAG["1.8"] == "1.3.1"
        assert RULE_TO_WCAG["1.9"] == "3.1.1"


class TestVeraPDFRunner:
    def test_missing_verapdf_returns_passing_stub(self, tmp_path):
        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4\n")
        runner = VeraPDFRunner(verapdf_path="/non/existent/path/verapdf")
        result = runner.validate(str(fake_pdf))
        assert result.compliant is True
        assert result.raw_output == "verapdf_not_installed"

    def test_parse_output_handles_invalid_json(self):
        runner = VeraPDFRunner()
        result = runner._parse_output("not valid json", returncode=0)
        assert result.compliant is True
        assert result.score > 0

    def test_parse_output_with_passed_assertions(self):
        runner = VeraPDFRunner()
        data = {
            "testAssertions": [
                {"status": "PASSED", "ruleId": "1.1.1"},
                {"status": "PASSED", "ruleId": "1.2.1"},
                {"status": "PASSED", "ruleId": "1.3.1"},
            ]
        }
        result = runner._parse_output(json.dumps(data), returncode=0)
        assert result.compliant is True
        assert result.rules_passed == 3
        assert result.rules_total == 3
        assert result.score == 100

    def test_parse_output_with_failures(self):
        runner = VeraPDFRunner()
        data = {
            "testAssertions": [
                {"status": "PASSED", "ruleId": "1.1.1"},
                {"status": "FAILED", "ruleId": "1.2.1",
                 "message": "Figure missing Alt"},
                {"status": "FAILED", "ruleId": "1.8.3",
                 "message": "Heading level skipped"},
            ]
        }
        result = runner._parse_output(json.dumps(data), returncode=1)
        assert result.compliant is False
        assert result.rules_passed == 1
        assert result.rules_total == 3
        assert len(result.failures) == 2

    def test_failures_include_wcag_criterion_mapping(self):
        runner = VeraPDFRunner()
        data = {"testAssertions": [
            {"status": "FAILED", "ruleId": "1.2.1", "message": "No alt"},
        ]}
        result = runner._parse_output(json.dumps(data), returncode=1)
        assert result.failures[0].wcag_criterion == "1.1.1"


class TestValidationResultRemainingIssues:
    def test_returns_remaining_issues_grouped(self):
        failures = [
            ValidationFailure("1.2.1", "Alt missing", "critical", wcag_criterion="1.1.1"),
            ValidationFailure("1.2.2", "Alt missing", "critical", wcag_criterion="1.1.1"),
            ValidationFailure("1.8.1", "Heading skip", "critical", wcag_criterion="1.3.1"),
        ]
        result = ValidationResult(
            compliant=False, score=50,
            failures=failures, rules_passed=10, rules_total=13,
        )
        issues = result.get_remaining_issues()
        # Two unique criteria
        assert len(issues) == 2
        # 1.1.1 has 2 failures, 1.3.1 has 1
        alt_issue = next(i for i in issues if i.criterion == "1.1.1")
        assert alt_issue.count == 2
