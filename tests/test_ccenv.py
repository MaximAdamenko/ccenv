"""Unit tests for ccenv.

These tests never touch the real ~/.claude/ or ~/.ccenv/. They use pytest's
`tmp_path` fixture as a fake $HOME and pass it to the CLI via `--home`. A few
tests additionally use `unittest.mock` to verify filesystem-mutating calls
happen as expected.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Load the CLI by path — the executable is called `main` (no .py extension),
# so spec_from_file_location can't infer a loader and we have to supply one.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
CCENV_PATH = REPO_ROOT / "main"

loader = SourceFileLoader("ccenv", str(CCENV_PATH))
spec = importlib.util.spec_from_loader("ccenv", loader)
assert spec is not None
ccenv = importlib.util.module_from_spec(spec)
sys.modules["ccenv"] = ccenv
loader.exec_module(ccenv)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def home(tmp_path: Path) -> Path:
    """Fake $HOME for the duration of one test."""
    return tmp_path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_profile(
    profiles_dir: Path,
    name: str,
    *,
    mcp=None,
    skills=None,
    instructions: str | None = None,
) -> Path:
    """Construct a tiny profile directory inside *profiles_dir*."""
    p = profiles_dir / name
    p.mkdir(parents=True)

    _write(p / "CLAUDE.md", instructions if instructions is not None else f"# {name}\n")

    if mcp is None:
        mcp_text = json.dumps({"mcpServers": {}}, indent=2)
    elif isinstance(mcp, dict):
        mcp_text = json.dumps(mcp, indent=2)
    else:
        mcp_text = mcp
    _write(p / "mcp.json", mcp_text)

    skill_rel: list[str] = []
    for sk in skills or []:
        _write(p / "skills" / sk / "SKILL.md", f"# {sk}\n")
        skill_rel.append(f"skills/{sk}")

    yaml_lines = [
        f"name: {name}",
        f"description: {name} profile",
        "instructions: CLAUDE.md",
        "mcp_template: mcp.json",
        "skills:",
        *[f"  - {sp}" for sp in skill_rel],
    ]
    _write(p / "profile.yaml", "\n".join(yaml_lines) + "\n")
    return p


def _run(home: Path, *args: str) -> int:
    return ccenv.main(["--home", str(home), *args])


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

def test_init_creates_structure(home: Path):
    rc = _run(home, "init")
    assert rc == 0

    assert (home / ".ccenv").is_dir()
    assert (home / ".ccenv" / "profiles").is_dir()
    assert (home / ".ccenv" / ".env").is_file()
    assert (home / ".ccenv" / "state.json").is_file()

    state = json.loads((home / ".ccenv" / "state.json").read_text())
    assert state == {"active_profile": None}

    # An example profile gets laid down so new users have something to apply.
    assert (home / ".ccenv" / "profiles" / "example" / "profile.yaml").is_file()


def test_init_does_not_clobber_existing_secrets(home: Path):
    _run(home, "init")
    (home / ".ccenv" / ".env").write_text("FOO=bar\n")

    _run(home, "init")  # second run is a no-op for existing files

    assert (home / ".ccenv" / ".env").read_text() == "FOO=bar\n"


def test_init_does_not_touch_claude_dir(home: Path):
    (home / ".claude").mkdir()
    (home / ".claude" / "history.jsonl").write_text("preexisting\n")
    _run(home, "init")
    assert (home / ".claude" / "history.jsonl").read_text() == "preexisting\n"
    # ccenv must not create ~/.claude/ contents during init
    assert not (home / ".claude" / "CLAUDE.md").exists()


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------

def test_apply_writes_all_managed_targets(home: Path):
    _run(home, "init")
    _make_profile(home / ".ccenv" / "profiles", "devops",
                  skills=["terraform-helper", "jenkins-runner"])

    rc = _run(home, "apply", "devops")
    assert rc == 0

    claude = home / ".claude"
    assert (claude / "CLAUDE.md").read_text() == "# devops\n"
    assert json.loads((claude / "mcp.json").read_text()) == {"mcpServers": {}}
    assert (claude / "skills" / "terraform-helper" / "SKILL.md").is_file()
    assert (claude / "skills" / "jenkins-runner" / "SKILL.md").is_file()

    state = json.loads((home / ".ccenv" / "state.json").read_text())
    assert state["active_profile"] == "devops"


def test_apply_substitutes_secrets_into_mcp_json(home: Path):
    _run(home, "init")
    template = json.dumps({
        "mcpServers": {
            "github": {
                "command": "github-mcp",
                "env": {"TOKEN": "{{ GITHUB_TOKEN }}"},
            }
        }
    }, indent=2)
    _make_profile(home / ".ccenv" / "profiles", "devops", mcp=template)
    (home / ".ccenv" / ".env").write_text("GITHUB_TOKEN=ghp_abc123\n")

    _run(home, "apply", "devops")

    rendered = json.loads((home / ".claude" / "mcp.json").read_text())
    assert rendered["mcpServers"]["github"]["env"]["TOKEN"] == "ghp_abc123"
    # Placeholder syntax shouldn't survive into the output
    assert "{{" not in (home / ".claude" / "mcp.json").read_text()


def test_apply_missing_secret_fails_without_touching_disk(home: Path, capsys):
    _run(home, "init")
    template = json.dumps({"mcpServers": {"x": {"env": {"K": "{{ MISSING }}"}}}})
    _make_profile(home / ".ccenv" / "profiles", "devops", mcp=template)

    # Pre-existing managed file — proves we don't wipe before failing.
    (home / ".claude").mkdir()
    (home / ".claude" / "CLAUDE.md").write_text("OLD\n")

    rc = _run(home, "apply", "devops")
    assert rc == 1
    assert "MISSING" in capsys.readouterr().err
    assert (home / ".claude" / "CLAUDE.md").read_text() == "OLD\n"


def test_apply_unknown_profile_fails(home: Path, capsys):
    _run(home, "init")
    rc = _run(home, "apply", "does-not-exist")
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_apply_rejects_invalid_rendered_json(home: Path, capsys):
    _run(home, "init")
    # The template is non-JSON garbage; the renderer can substitute, but the
    # JSON validation step should catch it.
    _make_profile(home / ".ccenv" / "profiles", "broken", mcp="this is not { json")
    rc = _run(home, "apply", "broken")
    assert rc == 1
    assert "valid JSON" in capsys.readouterr().err
    # And we shouldn't have written anything inside ~/.claude/
    assert not (home / ".claude" / "mcp.json").exists()


# ---------------------------------------------------------------------------
# switch — the headline behavior: no leftovers
# ---------------------------------------------------------------------------

def test_switch_removes_previous_profiles_skills(home: Path):
    _run(home, "init")
    profiles = home / ".ccenv" / "profiles"
    _make_profile(profiles, "devops", skills=["terraform-helper", "jenkins-runner"])
    _make_profile(profiles, "frontend", skills=["react-conventions", "figma-bridge"])

    _run(home, "apply", "devops")
    assert (home / ".claude" / "skills" / "terraform-helper").is_dir()
    assert (home / ".claude" / "skills" / "jenkins-runner").is_dir()

    rc = _run(home, "switch", "frontend")
    assert rc == 0

    skills_dir = home / ".claude" / "skills"
    present = sorted(p.name for p in skills_dir.iterdir())
    assert present == ["figma-bridge", "react-conventions"]
    assert not (skills_dir / "terraform-helper").exists()
    assert not (skills_dir / "jenkins-runner").exists()

    assert (home / ".claude" / "CLAUDE.md").read_text() == "# frontend\n"

    state = json.loads((home / ".ccenv" / "state.json").read_text())
    assert state["active_profile"] == "frontend"


def test_switch_does_not_touch_unmanaged_files(home: Path):
    """The user's history and settings.json must survive a switch."""
    _run(home, "init")
    profiles = home / ".ccenv" / "profiles"
    _make_profile(profiles, "devops", skills=["terraform-helper"])
    _make_profile(profiles, "frontend", skills=["react-conventions"])

    (home / ".claude").mkdir()
    (home / ".claude" / "history.jsonl").write_text("user history\n")
    (home / ".claude" / "settings.json").write_text('{"a":1}')

    _run(home, "apply", "devops")
    _run(home, "switch", "frontend")

    assert (home / ".claude" / "history.jsonl").read_text() == "user history\n"
    assert (home / ".claude" / "settings.json").read_text() == '{"a":1}'


def test_switch_after_manual_junk_in_skills_dir(home: Path):
    """If the user manually drops junk under skills/, the next apply wipes it."""
    _run(home, "init")
    profiles = home / ".ccenv" / "profiles"
    _make_profile(profiles, "devops", skills=["terraform-helper"])
    _make_profile(profiles, "frontend", skills=["react-conventions"])

    _run(home, "apply", "devops")
    junk = home / ".claude" / "skills" / "manually-dropped-junk"
    junk.mkdir()
    (junk / "garbage.md").write_text("noise\n")

    _run(home, "switch", "frontend")
    assert not junk.exists()


def test_switch_repeated_to_same_profile_is_idempotent(home: Path):
    _run(home, "init")
    _make_profile(home / ".ccenv" / "profiles", "devops",
                  skills=["terraform-helper"])
    _run(home, "apply", "devops")
    _run(home, "switch", "devops")
    _run(home, "switch", "devops")
    assert (home / ".claude" / "skills" / "terraform-helper").is_dir()


def test_corrupt_state_file_yields_clean_error(home: Path):
    _run(home, "init")
    _make_profile(home / ".ccenv" / "profiles", "devops")
    (home / ".ccenv" / "state.json").write_text("not json")
    rc = _run(home, "switch", "devops")
    assert rc == 1


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def test_status_reports_active_profile(home: Path, capsys):
    _run(home, "init")
    _make_profile(home / ".ccenv" / "profiles", "devops")
    _run(home, "apply", "devops")
    capsys.readouterr()  # flush

    rc = _run(home, "status")
    assert rc == 0
    out = capsys.readouterr().out
    assert "Active profile: devops" in out
    assert "Available profiles" in out


def test_status_when_no_profile_active(home: Path, capsys):
    _run(home, "init")
    capsys.readouterr()
    rc = _run(home, "status")
    assert rc == 0
    assert "No profile is active" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Unit tests on the small helpers
# ---------------------------------------------------------------------------

def test_render_template_substitutes_all_tokens():
    out = ccenv._render_template("hello {{ A }} and {{ B }}", {"A": "x", "B": "y"})
    assert out == "hello x and y"


def test_render_template_missing_raises():
    with pytest.raises(ccenv.CcenvError) as exc:
        ccenv._render_template("{{ X }}", {})
    assert "X" in str(exc.value)


def test_render_template_whitespace_variants():
    out = ccenv._render_template("{{A}} {{  B  }}", {"A": "1", "B": "2"})
    assert out == "1 2"


def test_render_template_no_placeholders_is_pass_through():
    assert ccenv._render_template("no tokens here", {"X": "y"}) == "no tokens here"


# ---------------------------------------------------------------------------
# Mock-based tests — verify the wipe step is wired up correctly
# ---------------------------------------------------------------------------

def test_apply_invokes_rmtree_on_old_skills_dir(home: Path):
    """During a switch, the old skills/ must be removed via shutil.rmtree."""
    _run(home, "init")
    profiles = home / ".ccenv" / "profiles"
    _make_profile(profiles, "devops", skills=["terraform-helper"])
    _make_profile(profiles, "frontend", skills=["react-conventions"])

    _run(home, "apply", "devops")

    with mock.patch.object(ccenv.shutil, "rmtree", wraps=ccenv.shutil.rmtree) as m:
        _run(home, "switch", "frontend")

    rmtree_targets = [str(call.args[0]) for call in m.call_args_list]
    assert any(str(home / ".claude" / "skills") in t for t in rmtree_targets), (
        f"expected rmtree to be called on the skills dir, got {rmtree_targets}"
    )


def test_apply_unlinks_old_managed_files(home: Path):
    """The old CLAUDE.md / mcp.json must be unlink()ed before being rewritten."""
    _run(home, "init")
    profiles = home / ".ccenv" / "profiles"
    _make_profile(profiles, "devops")
    _make_profile(profiles, "frontend")

    _run(home, "apply", "devops")

    real_unlink = Path.unlink
    seen: list[str] = []

    def spy(self, *a, **kw):
        seen.append(str(self))
        return real_unlink(self, *a, **kw)

    with mock.patch.object(Path, "unlink", spy):
        _run(home, "switch", "frontend")

    assert any("CLAUDE.md" in p for p in seen)
    assert any("mcp.json" in p for p in seen)


def test_main_defaults_home_to_expanduser(monkeypatch, tmp_path):
    """When --home is omitted, the CLI uses Path(os.path.expanduser('~'))."""
    fake = tmp_path / "fakehome"
    fake.mkdir()
    # We don't actually want to execute init against the patched home — we
    # just want to confirm Config picks up the user's HOME. Mock cmd_init.
    monkeypatch.setattr(ccenv.os.path, "expanduser",
                        lambda p: str(fake) if p == "~" else p)

    captured: dict[str, ccenv.Config] = {}

    def fake_init(cfg):
        captured["cfg"] = cfg
        return 0

    monkeypatch.setattr(ccenv, "cmd_init", fake_init)
    rc = ccenv.main(["init"])
    assert rc == 0
    assert str(captured["cfg"].home) == str(fake)
