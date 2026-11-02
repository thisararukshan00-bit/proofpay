"""Deterministic checks. These run in plain code; the AI can never override their verdict."""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

from .deliverable import Deliverable

# The only checks the Criteria Builder (AI or demo) may use. Anything else becomes an ai_review criterion.
CHECK_CATALOG = {
    "readme_exists": "Repository has a README file.",
    "readme_has_section": "README has a heading matching param (e.g. 'run|usage|install|setup').",
    "license_exists": "Repository has a LICENSE file.",
    "file_exists": "A file matching the glob in param exists (e.g. 'docs/*.md').",
    "tests_exist": "Repository contains tests (a test directory or test_* / *.test.* files).",
    "ci_passing": "The latest commit's GitHub checks / CI passed.",
    "min_words": "Primary text (document, or README for a repo) has at least param words.",
    "text_contains": "Some submitted file contains the phrase in param (case-insensitive).",
}


@dataclass
class CheckResult:
    verdict: str  # pass | fail | unclear
    explanation: str
    evidence: list = field(default_factory=list)  # [{"path":..., "quote":..., "verified": True}]


def _evidence(path: str, quote: str) -> dict:
    return {"path": path, "quote": quote[:300], "verified": True}


def run_check(name: str, param, d: Deliverable) -> CheckResult:
    fn = _CHECKS.get(name)
    if fn is None:
        return CheckResult("unclear", f"Unknown check '{name}'.")
    try:
        return fn(param, d)
    except re.error:
        return CheckResult("unclear", "The check pattern was invalid.")


def _need_github(d: Deliverable, what: str):
    if d.kind != "github":
        return CheckResult("unclear", f"{what} only applies to a GitHub repository submission.")
    return None


def _readme_exists(_p, d):
    if (r := _need_github(d, "README check")):
        return r
    for path in d.tree:
        if "/" not in path and path.lower().startswith("readme"):
            return CheckResult("pass", f"Found {path} in the repository root.", [_evidence(path, "(file present)")])
    return CheckResult("fail", "No README file in the repository root.")


def _readme_has_section(param, d):
    if (r := _need_github(d, "README check")):
        return r
    words = str(param or "run|usage|install|setup")
    # The pattern may come from the AI, so allow only plain words joined by '|' (no regex features, no ReDoS).
    if not re.fullmatch(r"[A-Za-z0-9 _-]{1,30}(\|[A-Za-z0-9 _-]{1,30}){0,7}", words):
        return CheckResult("unclear", "The heading pattern was not valid.")
    pattern = re.compile(rf"^#{{1,6}}[^\n]*({words})[^\n]*$", re.I | re.M)
    for path, text in d.files.items():
        if "/" not in path and path.lower().startswith("readme"):
            m = pattern.search(text)
            if m:
                return CheckResult("pass", "README has a matching heading.", [_evidence(path, m.group(0).strip())])
            return CheckResult("fail", f"README has no heading matching '{words}'.")
    return CheckResult("fail", "No README file was available to read.")


def _license_exists(_p, d):
    if (r := _need_github(d, "License check")):
        return r
    for path in d.tree:
        if "/" not in path and re.match(r"^(licen[sc]e|copying)", path, re.I):
            return CheckResult("pass", f"Found {path} in the repository root.", [_evidence(path, "(file present)")])
    return CheckResult("fail", "No LICENSE file in the repository root.")


def _file_exists(param, d):
    if not param:
        return CheckResult("unclear", "No file pattern was given.")
    for path in d.tree:
        if fnmatch.fnmatch(path.lower(), str(param).lower()):
            return CheckResult("pass", f"Found {path}.", [_evidence(path, "(file present)")])
    note = " (the file list was truncated by GitHub)" if d.truncated_tree else ""
    return CheckResult("fail", f"No file matches '{param}'{note}.")


def _tests_exist(_p, d):
    if (r := _need_github(d, "Test check")):
        return r
    for path in d.tree:
        low = path.lower()
        name = low.rsplit("/", 1)[-1]
        if (re.search(r"(^|/)(tests?|__tests__|spec)/", low) or name.startswith("test_")
                or re.search(r"\.(test|spec)\.[a-z]+$", name) or name.endswith("_test.py")):
            return CheckResult("pass", f"Found test file {path}.", [_evidence(path, "(file present)")])
    return CheckResult("fail", "No test directory or test files were found.")


def _ci_passing(_p, d):
    if (r := _need_github(d, "CI check")):
        return r
    if d.ci == "success":
        return CheckResult("pass", "The latest commit's checks all succeeded.", [_evidence("(GitHub checks)", "success")])
    if d.ci == "failure":
        return CheckResult("fail", "At least one check on the latest commit failed.")
    if d.ci == "none":
        return CheckResult("fail", "The latest commit has no CI checks.")
    return CheckResult("unclear", "CI checks are still running or their state is unknown.")


def _min_words(param, d):
    try:
        needed = int(param)
    except (TypeError, ValueError):
        return CheckResult("unclear", "No word count target was given.")
    text = d.primary_text
    if not text:
        return CheckResult("fail", "There is no document or README text to count.")
    words = len(re.findall(r"\S+", text))
    where = "document" if d.kind == "text" else "README"
    ev = [_evidence(d.label if d.kind == "text" else "README", f"{words} words counted")]
    if words >= needed:
        return CheckResult("pass", f"The {where} has {words} words (needed {needed}).", ev)
    return CheckResult("fail", f"The {where} has {words} words (needed {needed}).", ev)


def _text_contains(param, d):
    phrase = str(param or "").strip()
    if len(phrase) < 3:
        return CheckResult("unclear", "No phrase was given.")
    low = phrase.lower()
    for path, text in d.files.items():
        idx = text.lower().find(low)
        if idx >= 0:
            start = max(0, idx - 40)
            return CheckResult("pass", f"Found '{phrase}'.", [_evidence(path, text[start: idx + len(phrase) + 40].strip())])
    return CheckResult("fail", f"'{phrase}' was not found in the files we could read.")


_CHECKS = {
    "readme_exists": _readme_exists,
    "readme_has_section": _readme_has_section,
    "license_exists": _license_exists,
    "file_exists": _file_exists,
    "tests_exist": _tests_exist,
    "ci_passing": _ci_passing,
    "min_words": _min_words,
    "text_contains": _text_contains,
}
