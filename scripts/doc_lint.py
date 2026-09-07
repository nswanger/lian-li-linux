"""doc_lint — mechanical checks for the project documentation framework.

Checks what `references/framework.md` asserts and nothing enforces. Scoped to
the LIVING surface (guide, shims, glossary, runbooks, folder READMEs) plus the
decision records, so ephemera (specs, plans, archives) never generate noise.

Checks:
  file-refs      linked / backticked repo paths in living docs exist and
                 are not archived
  anchors        `#fragment` links in living docs resolve to a real heading
  decisions      every record carries an ISO date and a named decider
  archive-links  no living doc links into an archive dir
  archive-banner every archived .md starts with the "> Archived" banner
  readme-map     every folder README is named in the guide's directory map
  root-docs      every root-level .md is in the living surface
  forbidden      no status doc, open-questions doc, or handoff dir exists;
                 no living doc carries a pending/status section
  living-set     every `living` entry in the config resolves to a real path
  cap            guide + shims stay under the token cap
  sql-objects    (opt-in) typed-prefix object names in living docs exist in sql/

Usage:
    python doc_lint.py                 # report to stdout
    python doc_lint.py --strict        # exit 1 on any finding (CI / hook)
    python doc_lint.py --report        # also write DOC_LINT.md at repo root
    python doc_lint.py --config path   # default: <repo>/doc-lint.toml

Stdlib only (Python 3.11+ for tomllib). Repo root = the directory holding
doc-lint.toml, found by walking up from cwd.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import time
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib
from datetime import date
from pathlib import Path

DEFAULTS: dict = {
    "guide": "AGENTS.md",
    "shims": ["CLAUDE.md"],   # add the applyTo shim here only if the repo has one
    "glossary": "CONTEXT.md",
    "decisions": "docs/decisions",
    "living": ["README.md", "docs/runbooks"],
    "archive_dirs": ["_archive"],
    "ephemera": ["docs/specs", "docs/plans", "docs/research", "docs/maps",
                 "docs/superpowers", ".scratch", ".superpowers"],
    "skip_dirs": [".git", "node_modules", ".venv", "__pycache__", ".pytest_cache",
                  "dist", "build", ".claude", ".snowflake", "test-results"],
    "forbidden_paths": ["docs/handoffs", "docs/STATUS.md", "docs/open-questions.md"],
    "generated": [],          # glob patterns for generated/gitignored outputs docs may name
    "root_docs_exempt": ["DOC_LINT.md", "LICENSE.md", "CHANGELOG.md",
                         "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md"],
    "token_cap": 2000,
    "checks": {"sql_objects": False},
    "sql": {"dir": "sql", "object_pattern": ""},
}

PATH_TOKEN = re.compile(
    r"(?:\]\(|`)((?:[\w.\-]+/)*[\w.\-]+\.(?:sql|py|md|csv|js|ts|tsx|json|yml|yaml|toml|txt|sh|ps1|html|css))(?:\)|`|#)")
STATUS_FILENAME = re.compile(
    r"(progress|status|open-questions|open_questions|handoff|continuation)", re.I)
STATUS_HEADING = re.compile(
    r"^#{2,4}\s.*\b(open questions?|continuation point|remaining (work|gates?)|"
    r"implementation progress|current status|latest verification|next steps)\b", re.I)
DECIDED_LINE = re.compile(r"Decided by .+? on (\d{4}-\d{2}-\d{2})")
BANNER = re.compile(r"^> Archived \d{4}-\d{2}-\d{2}")
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.M)
INLINE_MARKUP = re.compile(r"<[^>]+>|`+|\*\*|\*|~~|__")
LINK_TEXT = re.compile(r"\[([^\]]*)\]\([^)]*\)")
EXPLICIT_ID = re.compile(r'<a\s+(?:id|name)="([^"]+)"|\{#([\w-]+)\}')
LINE_SUFFIX = re.compile(r":\d+(?:-\d+)?$")


# ---------------------------------------------------------------- setup

def find_repo(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "doc-lint.toml").exists():
            return p
    sys.exit("doc_lint: no doc-lint.toml found walking up from cwd")


def load_config(repo: Path, path: Path | None) -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    cfg_path = path or repo / "doc-lint.toml"
    if cfg_path.exists():
        user = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


class Lint:
    def __init__(self, repo: Path, cfg: dict):
        self.repo = repo
        self.cfg = cfg
        self.guide = repo / cfg["guide"]
        self.shims = [repo / s for s in cfg["shims"]]
        self.decisions_dir = repo / cfg["decisions"]
        self.living = self._living_docs()

    # -- helpers
    def rel(self, p: Path) -> str:
        return p.relative_to(self.repo).as_posix()

    def read(self, p: Path) -> str:
        return p.read_text(encoding="utf-8", errors="ignore")

    def in_skipped(self, p: Path) -> bool:
        rel = self.rel(p)
        parts = set(p.relative_to(self.repo).parts)
        if parts & set(self.cfg["skip_dirs"]):
            return True
        if parts & set(self.cfg["archive_dirs"]):
            return True
        return any(rel == e or rel.startswith(e + "/") for e in self.cfg["ephemera"])

    def _living_docs(self) -> list[Path]:
        out: list[Path] = []
        self.living_missing: list[str] = []
        candidates = [self.guide, *self.shims, self.repo / self.cfg["glossary"]]
        for entry in self.cfg["living"]:
            p = self.repo / entry
            if p.is_dir():
                candidates += sorted(p.rglob("*.md"))
            else:
                if not p.exists():
                    self.living_missing.append(entry)
                candidates.append(p)
        candidates += sorted(self.repo.rglob("README.md"))
        for p in candidates:
            if p.exists() and p.is_file() and not self.in_skipped(p) and p not in out:
                out.append(p)
        return out

    # -- checks
    def check_file_refs(self) -> list[str]:
        findings = []
        # Split live from archived. The suffix fallback below exists so a doc can
        # name `foo/bar.sql` from anywhere in the tree, but matching it against an
        # archived file silently blesses a link that 404s and points at
        # non-authoritative content - the thing archive-links forbids.
        live_files, archived_files = [], []
        for p in self.repo.rglob("*"):
            if not p.is_file():
                continue
            parts = set(p.relative_to(self.repo).parts)
            if parts & set(self.cfg["skip_dirs"]):
                continue
            bucket = archived_files if parts & set(self.cfg["archive_dirs"]) else live_files
            bucket.append(self.rel(p))
        for doc in self.living:
            text = self.read(doc)
            for m in PATH_TOKEN.finditer(text):
                ref = m.group(1)
                if ref.startswith(("http", "www.")) or "*" in ref or "<" in ref:
                    continue
                ref = ref.removeprefix("./")
                if (doc.parent / ref).exists() or (self.repo / ref).exists():
                    continue
                if any(f.endswith("/" + ref) or f == ref for f in live_files):
                    continue
                if any(fnmatch.fnmatch(ref, g) or fnmatch.fnmatch(Path(ref).name, g)
                       for g in self.cfg["generated"]):
                    continue
                hit = next((f for f in archived_files
                            if f.endswith("/" + ref) or f == ref), None)
                if hit and "/" not in ref:
                    continue      # a bare filename named generically in prose
                                  # (`ARCHIVE.md`), not a link to one file
                if hit:
                    f = (f"{self.rel(doc)}: `{ref}` is archived at `{hit}` \u2014 living "
                         f"docs never link into an archive; drop the reference, or point "
                         f"at the durable home its content was extracted to")
                else:
                    f = f"{self.rel(doc)}: referenced path does not exist: `{ref}`"
                if f not in findings:
                    findings.append(f)
        return findings

    def check_anchors(self) -> list[str]:
        # `#fragment` links never reach check_file_refs: PATH_TOKEN requires a
        # file extension, so a bare fragment is invisible and a `file.md#frag`
        # link is only checked as far as the file. A section deleted under the
        # status-doc ban leaves its inbound links behind; this catches them.
        findings = []
        for doc in self.living:
            text = self.read(doc)
            own = anchors_of(text)
            for m in MD_LINK.finditer(text):
                href = m.group(1)
                if href.startswith(("http", "www.", "mailto:")):
                    continue
                path, _, frag = href.partition("#")
                if not frag:
                    continue
                path = LINE_SUFFIX.sub("", path.removeprefix("./"))
                if not path:
                    if frag.lower() not in own:
                        findings.append(
                            f"{self.rel(doc)}: `#{frag}` matches no heading in this file")
                    continue
                if not path.endswith(".md"):
                    continue
                cand = doc.parent / path
                target = cand if cand.exists() else self.repo / path
                if not target.exists():
                    continue          # file-refs owns the missing file
                try:
                    parts = set(target.resolve().relative_to(self.repo.resolve()).parts)
                except ValueError:
                    continue          # outside the repo
                if parts & set(self.cfg["archive_dirs"]):
                    continue          # archive-links / file-refs own those
                if frag.lower() not in anchors_of(self.read(target)):
                    findings.append(
                        f"{self.rel(doc)}: `{path}#{frag}` matches no heading in that file")
        return findings

    def check_living_set(self) -> list[str]:
        # A `living` entry that resolves to nothing is dropped silently, which is
        # the "enforced by nothing" trap running backwards: one typo takes a doc
        # out of coverage with no signal at all.
        return [f"`{e}` is in the config\u2019s `living` list but does not exist "
                f"\u2014 create it, or drop the entry"
                for e in self.living_missing]

    def check_decisions(self) -> list[str]:
        # The dir is optional (personal repos usually lack it). Where it exists,
        # each record's contract is one line: an ISO date and a named decider,
        # either as a `Decided by <name> on YYYY-MM-DD` line near the top or as
        # legacy v1 frontmatter with valid `date` and `deciders`.
        findings = []
        if not self.decisions_dir.exists():
            return findings
        files = sorted(p for p in self.decisions_dir.glob("*.md")
                       if not set(p.parts) & set(self.cfg["archive_dirs"]))
        for p in files:
            rel = self.rel(p)
            text = self.read(p)
            fm = parse_frontmatter(text)
            if fm is not None:
                if valid_date(fm.get("date")) and fm.get("deciders") not in ("", [], None):
                    continue
                findings.append(f"{rel}: frontmatter lacks a valid `date` + `deciders`")
                continue
            head = "\n".join(text.lstrip().splitlines()[:6])
            if not DECIDED_LINE.search(head):
                findings.append(
                    f"{rel}: first lines lack `Decided by <name> on YYYY-MM-DD`")
        return findings

    def check_archive_links(self) -> list[str]:
        findings = []
        names = self.cfg["archive_dirs"]
        pat = re.compile(r"(?:\]\(|`)([^)`\s]*(?:" + "|".join(map(re.escape, names)) + r")/[^)`\s]+)")
        for doc in self.living:
            for m in pat.finditer(self.read(doc)):
                findings.append(f"{self.rel(doc)}: living doc links into an archive: `{m.group(1)}`")
        return findings

    def check_archive_banner(self) -> list[str]:
        findings = []
        for name in self.cfg["archive_dirs"]:
            for d in self.repo.rglob(name):
                if not d.is_dir() or set(d.relative_to(self.repo).parts) & set(self.cfg["skip_dirs"]):
                    continue
                for p in d.rglob("*.md"):
                    head = self.read(p).lstrip().splitlines()[:3]
                    if not any(BANNER.match(line) for line in head):
                        findings.append(f"{self.rel(p)}: archived file lacks `> Archived YYYY-MM-DD — …` banner")
        return findings

    def check_readme_map(self) -> list[str]:
        findings = []
        if not self.guide.exists():
            return [f"guide `{self.cfg['guide']}` missing"]
        guide = self.read(self.guide)
        for p in sorted(self.repo.rglob("README.md")):
            if p.parent == self.repo or self.in_skipped(p):
                continue
            folder = self.rel(p.parent)
            if f"`{folder}/`" in guide or f"`{folder}`" in guide or f"`{p.parent.name}/`" in guide:
                continue
            findings.append(
                f"{self.rel(p)}: folder `{folder}/` is not in the guide's directory map "
                f"(add the row, or drop the README if no trigger applies)")
        return findings

    def check_root_docs(self) -> list[str]:
        # Root markdown is a small, deliberately prominent set: a file there is
        # either canonical or misplaced. `living` omitting one is the map/living
        # coupling drifting in the direction living-set cannot see, because
        # "which docs are canonical" is the question the config exists to answer.
        # A doc outside the living surface is read by agents and checked by
        # nothing: its stale paths, dead anchors, and the "Open questions"
        # section growing in it are all invisible.
        covered = {self.rel(p) for p in self.living}
        findings = []
        for p in sorted(self.repo.glob("*.md")):
            if self.rel(p) in covered:
                continue
            if any(fnmatch.fnmatch(p.name, g) for g in self.cfg["root_docs_exempt"]):
                continue
            findings.append(
                f"{p.name}: sits at the repo root but is outside the living surface "
                f"\u2014 add it to `living` and to the guide's directory map, or move it")
        return findings

    def check_forbidden(self) -> list[str]:
        findings = []
        for f in self.cfg["forbidden_paths"]:
            if (self.repo / f).exists():
                findings.append(f"`{f}` exists — status and pending items belong in the tracker")
        docs_dir = self.repo / "docs"
        if docs_dir.exists():
            for p in sorted(docs_dir.rglob("*.md")):
                if self.in_skipped(p) or p.is_relative_to(self.decisions_dir):
                    continue
                if STATUS_FILENAME.search(p.name):
                    findings.append(
                        f"{self.rel(p)}: status-shaped document — its rows belong in the tracker; "
                        f"archive or delete the file")
        for doc in self.living:
            for line in self.read(doc).splitlines():
                if STATUS_HEADING.match(line):
                    findings.append(
                        f"{self.rel(doc)}: section `{line.strip('# ').strip()}` looks like "
                        f"status/pending content — move it to the tracker")
        return findings

    def check_cap(self) -> list[str]:
        words = 0
        for p in (self.guide, *self.shims):
            if p.exists():
                words += len(self.read(p).split())
        tokens = int(words * 1.35)
        if tokens > self.cfg["token_cap"]:
            return [f"guide + shims ≈ {tokens} tokens, over the {self.cfg['token_cap']} cap"]
        return []

    def check_sql_objects(self) -> list[str]:
        if not self.cfg["checks"].get("sql_objects"):
            return []
        pat = self.cfg["sql"].get("object_pattern")
        if not pat:
            return ["checks.sql_objects is on but sql.object_pattern is empty"]
        token = re.compile(pat)
        sql_text = "\n".join(
            self.read(p).upper() for p in (self.repo / self.cfg["sql"]["dir"]).rglob("*.sql")
            if not set(p.parts) & set(self.cfg["archive_dirs"]))
        findings = []
        for doc in self.living:
            for t in sorted(set(token.findall(self.read(doc)))):
                if t not in sql_text:
                    findings.append(f"{self.rel(doc)}: object `{t}` not found under {self.cfg['sql']['dir']}/")
        return findings


# ---------------------------------------------------------------- utils

def gh_slug(text: str) -> str:
    """GitHub's heading slug: lowercase, drop punctuation, ONE hyphen per space.
    Collapsing runs of spaces is the classic bug here - `A & B` renders two
    spaces once `&` is dropped, so its real anchor is `a--b`."""
    return re.sub(r"[^\w\s-]", "", text.strip().lower()).replace(" ", "-")


def anchors_of(text: str) -> set[str]:
    """Every anchor a document offers. GitHub slugs *rendered* text and we do not
    render, so each heading registers both its raw and its markup-stripped slug: a
    false positive here is worse than a miss, because noise is what gets a check
    switched off."""
    out: set[str] = set()
    for m in EXPLICIT_ID.finditer(text):
        out.add((m.group(1) or m.group(2)).lower())
    for raw in HEADING.findall(text):
        out.add(gh_slug(raw))
        out.add(gh_slug(INLINE_MARKUP.sub("", LINK_TEXT.sub(r"\1", raw))))
    return out


def parse_frontmatter(text: str) -> dict | None:
    """Minimal YAML subset: `key: value`, `key: [a, b]`, `key:` (null)."""
    lines = text.lstrip().splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    out: dict = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        if ":" not in line or line.startswith((" ", "\t", "#")):
            continue
        key, _, val = line.partition(":")
        val = val.split(" #", 1)[0].strip()
        if val.startswith("[") and val.endswith("]"):
            out[key.strip()] = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
        else:
            out[key.strip()] = val.strip("'\"") or None
    return None


def valid_date(v) -> bool:
    try:
        return isinstance(v, str) and bool(date.fromisoformat(v))
    except ValueError:
        return False


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="exit 1 on any finding")
    ap.add_argument("--report", action="store_true", help="write DOC_LINT.md at repo root")
    ap.add_argument("--config", type=Path)
    args = ap.parse_args()

    repo = find_repo(Path.cwd())
    lint = Lint(repo, load_config(repo, args.config))
    sections = {
        "file-refs": lint.check_file_refs(),
        "anchors": lint.check_anchors(),
        "decisions": lint.check_decisions(),
        "archive-links": lint.check_archive_links(),
        "archive-banner": lint.check_archive_banner(),
        "readme-map": lint.check_readme_map(),
        "root-docs": lint.check_root_docs(),
        "forbidden": lint.check_forbidden(),
        "living-set": lint.check_living_set(),
        "cap": lint.check_cap(),
        "sql-objects": lint.check_sql_objects(),
    }
    total = sum(len(v) for v in sections.values())
    lines = [f"# Doc Lint — {time.strftime('%Y-%m-%d %H:%M')}", "",
             f"**{total} finding(s)** across {len(lint.living)} living docs.", ""]
    for name, items in sections.items():
        lines.append(f"## {name} ({len(items)})")
        lines += [f"- {i}" for i in items] or ["- clean"]
        lines.append("")
    report = "\n".join(lines)
    print(report)
    if args.report:
        (repo / "DOC_LINT.md").write_text(report, encoding="utf-8")
    return 1 if (args.strict and total) else 0


if __name__ == "__main__":
    sys.exit(main())
