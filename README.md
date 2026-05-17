# ccenv

A minimal Claude Code environment manager. Declare role-specific profiles
(`devops`, `frontend`, …) and switch between them with one command. The
tool guarantees that nothing from the previous profile is left behind inside
`~/.claude/`.

## Install

Requires Python 3.9+ on macOS or Linux.

```bash
git clone <this-repo> ccenv && cd ccenv
pip install -r requirements.txt
chmod +x ccenv

# Optional: put it on your PATH
ln -s "$PWD/ccenv" /usr/local/bin/ccenv
```

## Five-minute start

1. **Initialise.**

   ```bash
   ./ccenv init
   ```

   This creates `~/.ccenv/` with `profiles/`, an empty `secrets.yaml`
   (mode `0600`), and a `state.json`. Your existing `~/.claude/` is *not*
   touched.

2. **Copy the example profiles in.**

   ```bash
   cp -R profiles/devops   ~/.ccenv/profiles/
   cp -R profiles/frontend ~/.ccenv/profiles/
   ```

3. **Add your secrets.** Edit `~/.ccenv/secrets.yaml`:

   ```yaml
   GITHUB_TOKEN:  ghp_xxxxxxxxxxxxxxxxxxxx
   JENKINS_TOKEN: jnkns_xxxxxxxxxxxxxxxxx
   FIGMA_API_KEY: figd_xxxxxxxxxxxxxxxxxxx
   ```

   The file lives outside the repo and is created with mode `0600` — never
   commit it.

4. **Apply a profile.**

   ```bash
   ./ccenv apply devops
   ./ccenv status
   ```

   Inspect `~/.claude/`:

   ```text
   ~/.claude/
   ├── CLAUDE.md        # the devops instructions
   ├── mcp.json         # rendered: {{ GITHUB_TOKEN }} substituted in
   └── skills/
       ├── terraform-helper/
       └── jenkins-runner/
   ```

5. **Switch.**

   ```bash
   ./ccenv switch frontend
   ls ~/.claude/skills/
   # figma-bridge   react-conventions     ← no devops leftovers
   ```

## Commands

| Command                  | What it does                                          |
| ------------------------ | ----------------------------------------------------- |
| `ccenv init`             | Create `~/.ccenv/` with empty secrets and state.      |
| `ccenv apply <profile>`  | Wipe managed contents of `~/.claude/`, write profile. |
| `ccenv switch <profile>` | Same as apply; logs the previous → next switch.       |
| `ccenv status`           | Show the active profile and list available profiles.  |

## Writing your own profile

A profile is a directory under `~/.ccenv/profiles/<name>/` with this layout:

```
<name>/
├── profile.yaml      # manifest (see below)
├── CLAUDE.md         # the instruction file
├── mcp.json          # MCP template (may contain {{ SECRET_NAME }})
└── skills/
    └── my-skill/
        └── SKILL.md
```

`profile.yaml`:

```yaml
name: myprofile
description: One-line summary.
instructions: CLAUDE.md
mcp_template: mcp.json
skills:
  - skills/my-skill
```

Any `{{ TOKEN }}` placeholder in `mcp.json` is substituted from
`~/.ccenv/secrets.yaml` at `apply` time. Missing secrets fail loudly without
modifying `~/.claude/`.

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

Tests use a fake `$HOME` (pytest's `tmp_path`) plus `unittest.mock` — they
never touch your real `~/.claude/` or `~/.ccenv/`.

## Project layout

```
ccenv                      # the CLI (single file, executable)
profiles/                  # example profiles to copy into ~/.ccenv/profiles/
  ├── devops/
  └── frontend/
tests/test_ccenv.py        # pytest suite
.github/workflows/ci.yml   # CI: runs pytest on every push
requirements.txt
design.md                  # the writeup
```
