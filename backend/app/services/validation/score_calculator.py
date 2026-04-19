from app.models.accessibility import AccessibilityScore
from app.services.extraction.pdf_extractor import ExtractionResult


class ScoreCalculator:
    def calculate_before(self, extraction: ExtractionResult) -> AccessibilityScore:
        """Estimate score before remediation based on what we found."""
        score = 0
        criteria: dict[str, int] = {}

        if not extraction.needs_ocr:
            score += 15
            criteria["4.1.2"] = 50

        if not extraction.has_existing_tags:
            criteria["1.3.1"] = 0
            criteria["1.3.2"] = 0
            criteria["2.4.1"] = 0
            criteria["2.4.2"] = 0
            criteria["1.1.1"] = 0
            criteria["3.1.1"] = 0
        else:
            score += 20
            criteria["1.3.1"] = 40
            criteria["2.4.2"] = 50

        return AccessibilityScore(
            overall=max(0, min(100, score)),
            pdfua1_compliant=False,
            wcag21_aa_compliant=False,
            criteria_scores=criteria,
        )

    def calculate_after(self, validation) -> AccessibilityScore:
        total = validation.rules_total
        passed = validation.rules_passed
        failures = validation.failures

        if total == 0:
            overall = 85
        else:
            critical = sum(1 for f in failures if f.severity == "critical")
            major = sum(1 for f in failures if f.severity == "major")
            minor = sum(1 for f in failures if f.severity == "minor")
            penalty = (critical * 15) + (major * 5) + (minor * 2)
            base_score = int(passed / total * 100)
            overall = max(0, min(100, base_score - penalty))

        failed_criteria = {
            f.wcag_criterion for f in failures if f.wcag_criterion
        }
        all_criteria = [
            "1.1.1", "1.3.1", "1.3.2",
            "2.4.1", "2.4.2", "3.1.1", "4.1.2",
        ]
        criteria_scores = {
            c: 0 if c in failed_criteria else 100 for c in all_criteria
        }
        for criterion in failed_criteria:
            count = sum(1 for f in failures if f.wcag_criterion == criterion)
            criteria_scores[criterion] = max(0, 100 - count * 20)

        return AccessibilityScore(
            overall=overall,
            pdfua1_compliant=validation.compliant,
            wcag21_aa_compliant=overall >= 80,
            criteria_scores=criteria_scores,
            rules_passed=validation.rules_passed,
            rules_total=validation.rules_total,
        )
