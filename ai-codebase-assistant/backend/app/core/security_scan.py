"""
Two tiers of security scanning:

1. Python: shells out to `bandit`, a real, maintained static analyzer (AST-
   based, same family of tool as Semgrep) -- no point reinventing its rule
   set. This is the accurate path.
2. Every other language: a small set of regex heuristics for the highest-
   value, lowest-noise findings (hardcoded-looking secrets, obvious
   SQL string concatenation, `eval`/`exec` on external input). This is
   explicitly a fallback, not a Semgrep replacement -- it will miss things
   and occasionally flag a false positive; findings say `heuristic` so the
   UI can present it with appropriately less confidence than bandit's.

Swapping in real Semgrep for the other languages is a documented extension
point (see README) -- it needs a semgrep binary in the container, which is
a reasonable Docker image addition but out of scope for what this build
verified.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


@dataclass
class SecurityFinding:
    file_path: str
    line: int
    severity: str  # LOW | MEDIUM | HIGH
    confidence: str  # tool name for python (bandit), "heuristic" otherwise
    rule: str
    message: str


_SECRET_PATTERN = re.compile(
    r"""(?ix)
    \b(api[_-]?key|secret|password|token|access[_-]?key)\b\s*[:=]\s*
    ['"]([A-Za-z0-9_\-/+=]{12,})['"]
    """
)
_SQL_CONCAT_PATTERN = re.compile(
    r"""(?ix)
    (SELECT|INSERT|UPDATE|DELETE)\b[^'"]{0,80}["'][^"']*["']\s*\+\s*\w+
    """
)
_EVAL_PATTERN = re.compile(r"\b(eval|exec)\s*\(")

_PLACEHOLDER_VALUES = {"changeme", "your_api_key", "xxxxxxxxxxxx", "example", "test", "placeholder"}


def scan_python_file(abs_path: Path) -> list[SecurityFinding]:
    """Runs real bandit against a single file and parses its JSON output."""
    try:
        proc = subprocess.run(
            ["bandit", "-f", "json", "-q", str(abs_path)],
            capture_output=True, text=True, timeout=20,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if not proc.stdout.strip():
        return []
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    findings = []
    for item in payload.get("results", []):
        findings.append(
            SecurityFinding(
                file_path=str(abs_path), line=item.get("line_number", 1),
                severity=item.get("issue_severity", "LOW"), confidence="bandit",
                rule=item.get("test_id", "B000"), message=item.get("issue_text", "").strip(),
            )
        )
    return findings


def scan_generic_file(rel_path: str, source_text: str) -> list[SecurityFinding]:
    findings: list[SecurityFinding] = []
    lines = source_text.splitlines()
    for i, line in enumerate(lines, start=1):
        secret_match = _SECRET_PATTERN.search(line)
        if secret_match:
            value = secret_match.group(2).lower()
            if value not in _PLACEHOLDER_VALUES and not value.startswith("$") and "{{" not in value:
                findings.append(
                    SecurityFinding(
                        file_path=rel_path, line=i, severity="MEDIUM", confidence="heuristic",
                        rule="hardcoded-secret",
                        message="Looks like a hardcoded credential. Move it to an environment variable or secret store.",
                    )
                )
        if _SQL_CONCAT_PATTERN.search(line):
            findings.append(
                SecurityFinding(
                    file_path=rel_path, line=i, severity="HIGH", confidence="heuristic",
                    rule="sql-string-concat",
                    message="SQL string looks like it's built with concatenation. Use parameterized queries to avoid injection.",
                )
            )
        if _EVAL_PATTERN.search(line):
            findings.append(
                SecurityFinding(
                    file_path=rel_path, line=i, severity="HIGH", confidence="heuristic",
                    rule="dangerous-eval",
                    message="eval()/exec() on runtime input is a common injection vector. Avoid it or strictly allow-list input.",
                )
            )
    return findings


def scan_file(rel_path: str, abs_path: Path, language: str | None) -> list[SecurityFinding]:
    if language == "python":
        return scan_python_file(abs_path)
    try:
        text = abs_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return scan_generic_file(rel_path, text)


def rank_findings(findings: list[SecurityFinding]) -> list[SecurityFinding]:
    return sorted(findings, key=lambda f: -SEVERITY_ORDER.get(f.severity, 0))
