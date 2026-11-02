"""Deliverables: a public GitHub repo snapshot or a text document. Submitted content is untrusted data.

We never clone or execute submitted code. For GitHub we only read files through the REST API, and the only
host we ever call is api.github.com (the URL is parsed, never fetched directly), so a submitted URL cannot
be used to make the server request arbitrary addresses.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field

import httpx

from .util import sha256_text

GITHUB_API = "https://api.github.com"
GITHUB_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/(?P<repo>[A-Za-z0-9._-]{1,100}?)"
    r"(?:\.git)?(?:/tree/(?P<branch>[A-Za-z0-9._/-]+))?/?$"
)
MAX_FILE_BYTES = 30_000
MAX_TOTAL_BYTES = 150_000
MAX_FILES = 14
TEXT_EXT = {".md", ".txt", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".html", ".css", ".yml", ".yaml",
            ".toml", ".cfg", ".ini", ".sh", ".java", ".cs", ".go", ".rs", ".rb", ".php", ".c", ".cpp", ".h"}
SKIP_PARTS = ("node_modules/", "dist/", "build/", ".git/", "__pycache__/", "vendor/", ".venv/")
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock"}
MAX_DOC_CHARS = 200_000


class DeliverableError(Exception):
    """The submission could not be read. The message is safe to show to users."""


@dataclass
class Deliverable:
    kind: str  # github | text
    label: str
    ref: str
    sha: str  # commit SHA for github, SHA-256 for text
    files: dict = field(default_factory=dict)  # path -> text content we actually read
    tree: list = field(default_factory=list)  # all file paths (github) or ["document"]
    ci: str = "unknown"  # success | failure | none | unknown
    commit_date: str = ""
    truncated_tree: bool = False

    @property
    def primary_text(self) -> str:
        if self.kind == "text":
            return self.files.get("document", "")
        for path, text in self.files.items():
            if path.lower().startswith("readme"):
                return text
        return ""


def from_text(text: str, filename: str = "document") -> Deliverable:
    text = (text or "").replace("\r\n", "\n")
    if len(text.strip()) < 20:
        raise DeliverableError("The document is empty or too short to verify.")
    if len(text) > MAX_DOC_CHARS:
        raise DeliverableError(f"The document is too long (limit {MAX_DOC_CHARS:,} characters).")
    digest = sha256_text(text)
    return Deliverable(kind="text", label=filename or "document", ref=f"sha256:{digest[:16]}", sha=digest,
                       files={"document": text}, tree=["document"])


def parse_github_url(url: str):
    m = GITHUB_URL_RE.match((url or "").strip())
    if not m:
        raise DeliverableError("Enter a public GitHub repository URL like https://github.com/owner/repo")
    return m.group("owner"), m.group("repo"), m.group("branch")


def _is_text_candidate(path: str, size: int) -> bool:
    low = path.lower()
    name = path.rsplit("/", 1)[-1]
    if size > MAX_FILE_BYTES or name in SKIP_NAMES:
        return False
    if any(part in low for part in SKIP_PARTS):
        return False
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ext in TEXT_EXT or name.upper().startswith(("LICENSE", "README"))


def _priority(path: str) -> tuple:
    low = path.lower()
    name = low.rsplit("/", 1)[-1]
    depth = low.count("/")
    if name.startswith("readme"):
        return (0, depth, low)
    if name.startswith("license"):
        return (1, depth, low)
    if name in {"package.json", "requirements.txt", "pyproject.toml", "pom.xml", "dockerfile"}:
        return (2, depth, low)
    if "test" in low:
        return (4, depth, low)
    return (3, depth, low)


def fetch_github(url: str, *, token: str = "", http: httpx.Client | None = None) -> Deliverable:
    owner, repo, branch = parse_github_url(url)
    client = http or httpx.Client(timeout=15.0)
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": "ProofPay-hackathon"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def get(path: str, accept: str | None = None):
        h = dict(headers)
        if accept:
            h["Accept"] = accept
        try:
            return client.get(f"{GITHUB_API}{path}", headers=h)
        except httpx.HTTPError as exc:
            raise DeliverableError(f"Could not reach GitHub ({exc.__class__.__name__}). Try again.") from exc

    meta = get(f"/repos/{owner}/{repo}")
    if meta.status_code == 404:
        raise DeliverableError("Repository not found. It must be public.")
    if meta.status_code in (403, 429):
        raise DeliverableError("GitHub rate limit reached. Set GITHUB_TOKEN or try again later.")
    if meta.status_code != 200:
        raise DeliverableError(f"GitHub returned HTTP {meta.status_code}.")
    info = meta.json()
    if info.get("private"):
        raise DeliverableError("Only public repositories can be verified.")
    ref_name = branch or info.get("default_branch", "main")

    commit = get(f"/repos/{owner}/{repo}/commits/{ref_name}")
    if commit.status_code != 200:
        raise DeliverableError("Could not read the latest commit of that branch.")
    cj = commit.json()
    sha = cj["sha"]
    commit_date = (cj.get("commit", {}).get("committer", {}) or {}).get("date", "")

    tree_resp = get(f"/repos/{owner}/{repo}/git/trees/{sha}?recursive=1")
    if tree_resp.status_code != 200:
        raise DeliverableError("Could not read the repository file list.")
    tj = tree_resp.json()
    blobs = [t for t in tj.get("tree", []) if t.get("type") == "blob"]
    tree_paths = [t["path"] for t in blobs]

    candidates = sorted((t for t in blobs if _is_text_candidate(t["path"], int(t.get("size", 0)))),
                        key=lambda t: _priority(t["path"]))
    files: dict = {}
    total = 0
    for item in candidates:
        if len(files) >= MAX_FILES or total >= MAX_TOTAL_BYTES:
            break
        resp = get(f"/repos/{owner}/{repo}/contents/{item['path']}?ref={sha}")
        if resp.status_code != 200:
            continue
        data = resp.json()
        if isinstance(data, dict) and data.get("encoding") == "base64":
            try:
                text = base64.b64decode(data.get("content", "")).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                continue
            files[item["path"]] = text
            total += len(text)

    ci = _ci_state(get, owner, repo, sha)
    return Deliverable(kind="github", label=f"{owner}/{repo}", ref=f"https://github.com/{owner}/{repo}@{sha[:10]}",
                       sha=sha, files=files, tree=tree_paths, ci=ci, commit_date=commit_date,
                       truncated_tree=bool(tj.get("truncated")))


def _ci_state(get, owner: str, repo: str, sha: str) -> str:
    conclusions = []
    runs = get(f"/repos/{owner}/{repo}/commits/{sha}/check-runs")
    if runs.status_code == 200:
        for run in runs.json().get("check_runs", []):
            conclusions.append(run.get("conclusion") or "pending")
    status = get(f"/repos/{owner}/{repo}/commits/{sha}/status")
    if status.status_code == 200 and status.json().get("total_count", 0) > 0:
        state = status.json().get("state")
        conclusions.append({"success": "success", "failure": "failure", "error": "failure"}.get(state, "pending"))
    if not conclusions:
        return "none"
    if any(c in {"failure", "timed_out", "cancelled", "action_required"} for c in conclusions):
        return "failure"
    if all(c in {"success", "neutral", "skipped"} for c in conclusions):
        return "success"
    return "unknown"
