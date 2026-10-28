import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "next_release.py"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _git("init", "-q", "-b", "main")
    _git("config", "user.name", "Test")
    _git("config", "user.email", "test@example.test")
    return tmp_path


def _git(*arguments):
    subprocess.run(["git", *arguments], check=True, capture_output=True)


def commit(message):
    _git("commit", "-q", "--allow-empty", "-m", message)


def release(*options):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *options], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def test_the_first_release_is_0_1_0(repo):
    commit("feat: start")
    assert release() == "0.1.0"


@pytest.mark.parametrize(
    ("messages", "version"),
    [
        (["docs: typo"], "1.2.4"),
        (["chore: tidy", "fix: a bug"], "1.2.4"),
        (["fix: a bug", "feat: a feature"], "1.3.0"),
        (["feat(codegen): a feature"], "1.3.0"),
        (["feat!: a breaking feature"], "2.0.0"),
        (["fix(api)!: a breaking fix"], "2.0.0"),
        (["refactor: rename", "fix: x\n\nBREAKING CHANGE: Client.get is gone"], "2.0.0"),
    ],
)
def test_the_bump_follows_the_commits_since_the_last_tag(repo, messages, version):
    commit("feat: before")
    _git("tag", "v1.2.3")
    for message in messages:
        commit(message)
    assert release() == version


def test_a_tagged_head_repeats_its_release(repo):
    commit("feat: one")
    _git("tag", "v1.0.0")
    commit("feat: two")
    _git("tag", "v1.1.0")
    assert release() == "1.1.0"
    assert "feat: two" in release("--notes") and "feat: one" not in release("--notes")


def test_other_tags_are_ignored(repo):
    commit("feat: one")
    _git("tag", "v1.0.0")
    _git("tag", "nightly")
    commit("fix: two")
    _git("tag", "v9.9.9-rc1")
    assert release() == "1.0.1"


def test_notes_group_the_commits(repo):
    commit("chore: before")
    _git("tag", "v1.0.0")
    for message in ["feat: add x", "fix: mend y", "docs: explain z", "feat!: drop w"]:
        commit(message)
    notes = release("--notes")
    assert notes.index("### Breaking changes") < notes.index("### Features")
    assert notes.index("### Fixes") < notes.index("### Other changes")
    assert "- feat: add x (" in notes and "- docs: explain z (" in notes
    assert notes.count("feat!: drop w") == 2  # under breaking changes and under features


def test_release_commits_are_left_out(repo):
    commit("feat: one")
    _git("tag", "v1.0.0")
    commit("chore(release): v1.0.0")
    commit("fix: two")
    assert release() == "1.0.1"
    assert "chore(release)" not in release("--notes")


CHANGELOG = """# Changelog

Notes before the releases.

## [1.0.0](https://github.com/o/r/compare/v0.9.0...v1.0.0) (2026-01-01)

### Features

- feat: one (1234567)
"""


def test_changelog_gets_the_release_above_the_newest_one(repo):
    commit("feat: one")
    _git("tag", "v1.0.0")
    _git("remote", "add", "origin", "git@github.com:o/r.git")
    commit("fix: mend")
    (repo / "CHANGELOG.md").write_text(CHANGELOG)
    assert release("--changelog", "CHANGELOG.md") == "1.0.1"
    text = (repo / "CHANGELOG.md").read_text()
    head, rest = text.split("## [1.0.1](https://github.com/o/r/compare/v1.0.0...v1.0.1) (")
    assert head == "# Changelog\n\nNotes before the releases.\n\n"
    assert rest.index("- fix: mend (") < rest.index("## [1.0.0]")
    assert rest.endswith(CHANGELOG.split("releases.\n\n")[1])


def test_the_first_changelog_entry_goes_at_the_end(repo):
    commit("feat: start")
    (repo / "CHANGELOG.md").write_text("# Changelog\n")
    assert release("--changelog", "CHANGELOG.md") == "0.1.0"
    assert (repo / "CHANGELOG.md").read_text().startswith("# Changelog\n\n## 0.1.0 (")
