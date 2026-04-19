import pytest

from app.services.validation.score_calculator import ScoreCalculator
from app.services.validation.verapdf_runner import ValidationResult, ValidationFailure
from app.services.extraction.pdf_extractor import ExtractionResult


def make_validation(passed: int, total: int, failures=None) -> ValidationResult:
    f = failures or []
    return ValidationResult(
        compliant=len(f) == 0,
        score=int(passed / total * 100) if total else 100,
        failures=f,
        rules_passed=passed,
        rules_total=total,
    )


class TestScoreCalculator:
    def setup_method(self):
        self.calc = ScoreCalculator()

    def test_perfect_score_when_all_pass(self):
        v = make_validation(23, 23)
        score = self.calc.calculate_after(v)
        assert score.overall == 100
        assert score.pdfua1_compliant is True
        assert score.wcag21_aa_compliant is True

    def test_zero_score_when_many_critical_failures(self):
        failures = [
            ValidationFailure(
                rule_id=f"1.2.{i}", description="alt text missing",
                severity="critical", wcag_criterion="1.1.1",
            )
            for i in range(8)
        ]
        v = make_validation(0, 23, failures)
        score = self.calc.calculate_after(v)
        assert score.overall <= 20

    def test_score_proportional_to_rules_passed(self):
        v = make_validation(18, 23)
        score = self.calc.calculate_after(v)
        assert score.overall >= 70

    def test_critical_failure_reduces_score_more_than_minor(self):
        critical_failure = [
            ValidationFailure("1.2.1", "Critical", "critical", wcag_criterion="1.1.1")
        ]
        minor_failure = [
            ValidationFailure("2.4.1", "Minor", "minor", wcag_criterion="2.4.1")
        ]
        v_critical = make_validation(22, 23, critical_failure)
        v_minor = make_validation(22, 23, minor_failure)
        s_critical = self.calc.calculate_after(v_critical)
        s_minor = self.calc.calculate_after(v_minor)
        assert s_critical.overall < s_minor.overall

    def test_before_score_zero_for_untagged_pdf(self):
        extraction = ExtractionResult(
            pages=[], page_count=5,
            needs_ocr=False, has_existing_tags=False,
        )
        score = self.calc.calculate_before(extraction)
        assert score.overall < 30
        assert score.pdfua1_compliant is False

    def test_wcag_aa_compliant_when_score_above_80(self):
        v = make_validation(22, 23)
        score = self.calc.calculate_after(v)
        assert score.wcag21_aa_compliant is True

    def test_wcag_aa_not_compliant_when_score_low(self):
        failures = [
            ValidationFailure(f"1.2.{i}", "critical", "critical", wcag_criterion="1.1.1")
            for i in range(5)
        ]
        v = make_validation(5, 23, failures)
        score = self.calc.calculate_after(v)
        assert score.wcag21_aa_compliant is False
