# ccenv — Design

`ccenv` is a small Python CLI that manages the three things Claude Code reads
out of `~/.claude/`: `CLAUDE.md`, `mcp.json`, and the `skills/` folder. Users
declare role-specific *profiles* (e.g. `devops`, `frontend`); the tool
materialises whichever one they pick into `~/.claude/` and guarantees that the
previous profile leaves no traces behind.

---

## 1. State: what gets written, removed, and left alone

The tool draws a sharp line between **managed** and **unmanaged** state inside
`~/.claude/`.

Managed (ccenv owns these — wipe before each apply):

- `~/.claude/CLAUDE.md`
- `~/.claude/mcp.json`
- `~/.claude/skills/`

Unmanaged (never touched):

- Anything else under `~/.claude/` — history, `settings.json`, caches,
  per-machine login state.

When `ccenv apply devops` runs:

1. Read `~/.ccenv/profiles/devops/profile.yaml`. That declares the
   instructions file, the MCP template, and a list of skill directories.
2. Load `~/.ccenv/secrets.yaml` and render the MCP template (`{{ TOKEN }}`
   placeholders → real values). If the rendered file isn't valid JSON, or any
   referenced secret is missing, the command aborts **before touching disk**,
   so we never produce a half-applied state.
3. Delete the three managed entries inside `~/.claude/` if they exist.
4. Copy `CLAUDE.md` over, write the rendered `mcp.json`, and `copytree` each
   skill directory into `~/.claude/skills/`.
5. Write `~/.ccenv/state.json` recording that `devops` is now active.

Concrete walk-through (`devops` already applied, user runs
`ccenv switch frontend`):

```
Before                                After
─────────                             ─────────
~/.claude/CLAUDE.md   (devops's)      ~/.claude/CLAUDE.md   (frontend's)
~/.claude/mcp.json    (devops's)      ~/.claude/mcp.json    (frontend's)
~/.claude/skills/                     ~/.claude/skills/
  ├── terraform-helper/                 ├── react-conventions/
  └── jenkins-runner/                   └── figma-bridge/
~/.claude/history.jsonl  (kept)       ~/.claude/history.jsonl  (still there)
~/.claude/settings.json  (kept)       ~/.claude/settings.json  (still there)
```

Everything else is "leave alone."

---

## 2. Switching cleanly

**Strategy:** every `apply` / `switch` does a *full wipe-then-write* of the
three managed targets. We don't try to diff old against new; we delete the
managed files/folders unconditionally and lay the new ones down.

**Why this works:**

- *Stateless w.r.t. the previous profile.* We don't need to remember what was
  applied last to clean it up — we wipe everything we manage every time.
- *Resilient to drift.* If a user manually drops a junk skill folder into
  `~/.claude/skills/`, the next `apply` tears it out automatically.
- *Bounded blast radius.* The list of paths we delete is the
  `MANAGED_FILES` / `MANAGED_DIRS` constants in `ccenv`. Anything outside
  those is untouchable, so the user's `history.jsonl` and `settings.json`
  survive.

**What could go wrong:**

- *Symlinks pointing out of `~/.claude/`.* We explicitly `unlink()` symlinks
  rather than walking them, so `rmtree` can't escape into the user's home.
- *A partial failure mid-copy* could in principle leave `~/.claude/` half
  populated. The mitigation is that the riskier work — template rendering and
  JSON validation — happens **before** the wipe. The remaining copy operations
  are mechanical and short.
- *Concurrent invocations.* No lock today. For a single-user CLI that's fine;
  a serious version would take an `fcntl.flock` on `~/.ccenv/state.json`.

---

## 3. Secrets

API tokens live in `~/.ccenv/secrets.yaml`, written with mode `0600`.
Profiles ship `mcp.json` templates with `{{ SECRET_NAME }}` placeholders; at
`apply` time, `ccenv` substitutes the values from the local secrets file and
writes the rendered JSON to `~/.claude/mcp.json`.

**Why that's safer than putting them in the profile:**

- Profile files are designed to be checked into Git and shared. A token
  committed to Git is a token leaked — once it's in the history, you must
  rotate it.
- `secrets.yaml` is per-machine, per-user, lives outside the repo, and is
  read-write only by the user. It never gets shared by accident because there
  is nothing to share — the profile references names, never values.
- The separation makes the rule obvious to a reviewer: profile is data,
  secrets are environment. That's a property worth preserving.

**Honest caveat:** `secrets.yaml` is plaintext on disk. A paranoid setup
would read from the macOS Keychain (`security find-generic-password`) or
`pass` / `gnome-keyring` on Linux. For a 12h exercise, a `0600` file in a
known location is the right tradeoff: simple, inspectable, and not in Git.

---

## 4. One thing I'd do differently with more time

**Add a `diff` (a.k.a. dry-run) command.** Right now `apply` is one-shot and
destructive; you learn what it did by reading the final state. With more time
I would add `ccenv diff <profile>` that:

1. Renders the new profile into a tempdir.
2. Walks the existing managed entries in `~/.claude/`.
3. Prints a structured summary — *would replace `CLAUDE.md`*, *would remove
   `skills/terraform-helper`*, *would add `skills/figma-bridge`*, *mcp.json
   servers added: `foo`, removed: `bar`*.
4. Optionally accepts `--apply` to commit the change atomically: stage the
   new content to a sibling tempdir under `~/.claude/`, then rename into
   place. That would make `apply` itself crash-safe — no half-applied states
   even if the process is killed mid-copy.

That single command would have caught most of the bugs I had to chase by hand
during development (particularly around the secrets template and the skills
list). It also doubles as documentation: a user can run `diff` to learn what a
profile *will* do before trusting it.
