"""Pydantic models for lint results.

This module defines the data structures for lint check results, following
the OpenAPI spec LintResult schema.

Classes:
    LintResult: Result of a lint check containing pass/fail status and violations
    GateCheckResult: Result of a single gate check
    GateResult: Result of all gate validations
"""

from datetime import datetime

from pydantic import BaseModel, Field


class LintResult(BaseModel):
    """Result of a lint check.

    Attributes:
        passed: True if no violations were found.
        violations: List of violation messages.
        checked_files: Number of files that were checked.
        checked_at: Timestamp when the check was performed.
    """

    passed: bool
    violations: list[str] = Field(default_factory=list)
    checked_files: int | None = None
    checked_at: datetime | None = None


class GateCheckResult(BaseModel):
    """Result of a single gate check.

    Attributes:
        gate_name: Name of the gate that was checked.
        passed: True if the gate check passed.
        violations: List of violation messages for this gate.
    """

    gate_name: str
    passed: bool
    violations: list[str] = Field(default_factory=list)


class GateResult(BaseModel):
    """Result of all gate validations.

    Attributes:
        passed: True if all gate checks passed.
        gates: List of individual gate check results.
    """

    passed: bool
    gates: list[GateCheckResult] = Field(default_factory=list)


__all__ = ["LintResult", "GateCheckResult", "GateResult"]
