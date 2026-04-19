from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BlockChange:
    block_id: str
    page_num: int
    change_type: str
    criterion: str
    before: Optional[str] = None
    after: Optional[str] = None
    confidence: float = 1.0


@dataclass
class AccessibilityScore:
    overall: int
    pdfua1_compliant: bool
    wcag21_aa_compliant: bool
    criteria_scores: dict = field(default_factory=dict)
    rules_passed: int = 0
    rules_total: int = 0


@dataclass
class RemainingIssue:
    criterion: str
    severity: str
    description: str
    count: int
    pages_affected: list[int] = field(default_factory=list)
