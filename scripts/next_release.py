"""The release for HEAD, from the conventional commits since the last tag.

    python scripts/next_release.py                          # the version, e.g. 2.4.0
    python scripts/next_release.py --notes                  # the release notes, in Markdown
    python scripts/next_release.py --changelog CHANGELOG.md # add the release to the changelog

Since the last vX.Y.Z tag: a breaking change (`feat!:`, or a BREAKING CHANGE footer) bumps the
major version, a `feat:` the minor, and anything else the patch, so every merge releases.
When a tag already points at HEAD, its version is the answer, so a rerun repeats a release
rather than making another. The release workflow's own `chore(release):` commits, which add
each release to the changelog, are left out. Standard library only: it runs before anything
is installed.
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
SUBJECT = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?(?P<breaking>!)?: ")
SECTIONS = {"feat": "Features", "fix": "Fixes", "perf": "Fixes"}
FIRST = (0, 1, 0)
RELEASE_COMMIT = "chore(release): "
GITHUB_REMOTE = re.compile(r"github\.com[:/](?P<repository>[^/]+/[^/]+?)(?:\.git)?$")


@dataclass
class Commit:
    sha: str
    subject: str
    body: str

    @property
    def type(self) -> str:
        match = SUBJECT.match(self.subject)
        return match["type"] if match else ""

    @property
    def breaking(self) -> bool:
        match = SUBJECT.match(self.subject)
        return bool(match and match["breaking"]) or "BREAKING CHANGE" in self.body


def git(*arguments: str) -> str:
    return subprocess.run(["git", *arguments], check=True, capture_output=True, text=True).stdout


def versions_at(revision: str) -> list[tuple[int, int, int]]:
    tags = git("tag", "--points-at", revision).split()
    return sorted(_version(tag) for tag in tags if TAG.match(tag))


def last_release() -> tuple[str | None, tuple[int, int, int] | None]:
    """The newest vX.Y.Z tag before HEAD, and its version; (None, None) if there is none."""
    tags = git("tag", "--merged", "HEAD", "--no-contains", "HEAD", "--list", "v*").split()
    released = sorted((_version(tag), tag) for tag in tags if TAG.match(tag))
    return (released[-1][1], released[-1][0]) if released else (None, None)


def commits_since(tag: str | None) -> list[Commit]:
    revisions = f"{tag}..HEAD" if tag else "HEAD"
    log = git("log", "--format=%H%x1f%s%x1f%b%x1e", revisions)
    entries = [entry.lstrip("\n") for entry in log.split("\x1e")]
    commits = [Commit(*entry.split("\x1f", 2)) for entry in entries if entry]
    return [commit for commit in commits if not commit.subject.startswith(RELEASE_COMMIT)]


def next_version(previous: tuple[int, int, int] | None, commits: list[Commit]) -> tuple:
    if previous is None:
        return FIRST
    major, minor, patch = previous
    if any(commit.breaking for commit in commits):
        return (major + 1, 0, 0)
    if any(commit.type == "feat" for commit in commits):
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)


def notes(commits: list[Commit]) -> str:
    sections: dict[str, list[str]] = {"Breaking changes": [], "Features": [], "Fixes": []}
    sections["Other changes"] = []
    for commit in commits:
        line = f"- {commit.subject} ({commit.sha[:7]})"
        if commit.breaking:
            sections["Breaking changes"].append(line)
        sections[SECTIONS.get(commit.type, "Other changes")].append(line)
    return "\n\n".join(
        f"### {title}\n\n" + "\n".join(lines) for title, lines in sections.items() if lines
    )


def add_to_changelog(path: Path, version: str, tag: str | None, commits: list[Commit]) -> None:
    """Puts the release above the newest one in the changelog (or at its end, if it has none)."""
    url = _repository_url()
    title = f"[{version}]({url}/compare/{tag}...v{version})" if url and tag else version
    entry = f"## {title} ({datetime.date.today().isoformat()})\n\n{notes(commits)}\n\n"
    text = path.read_text()
    newest = re.search(r"^## ", text, re.MULTILINE)
    at = newest.start() if newest else len(text.rstrip("\n")) + 1
    path.write_text(text[:at].rstrip("\n") + "\n\n" + entry + text[at:].lstrip("\n"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--notes", action="store_true", help="print the release notes")
    parser.add_argument("--changelog", type=Path, help="add the release to this changelog")
    arguments = parser.parse_args()
    tag, previous = last_release()
    commits = commits_since(tag)
    if arguments.notes:
        print(notes(commits))
        return
    tagged = versions_at("HEAD")
    version = ".".join(map(str, tagged[-1] if tagged else next_version(previous, commits)))
    if arguments.changelog:
        add_to_changelog(arguments.changelog, version, tag, commits)
    print(version)


def _repository_url() -> str | None:
    """The GitHub address of the origin remote, for compare links."""
    remote = git("remote", "get-url", "origin").strip() if git("remote").split() else ""
    match = GITHUB_REMOTE.search(remote)
    return f"https://github.com/{match['repository']}" if match else None


def _version(tag: str) -> tuple[int, int, int]:
    major, minor, patch = TAG.match(tag).groups()
    return (int(major), int(minor), int(patch))


if __name__ == "__main__":
    main()
