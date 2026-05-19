# ccenv

## What's New in This Version

**Per-Agent Isolated Memory:**
- Each agent (`devops`, `frontend`, `cicd`) has its own `Memory_Logs/` directory
- Memory includes: Sessions, Lessons, Preferences, Checkpoint, Context, Notes
- Memory NEVER leaks across agents—switching clears the previous agent's context
- Log sessions with `ccenv memory log <agent> "<summary>"`

**Team Coordination:**
- Shared `Brief.md` — project state, team status, recent activity
- Shared `Registry.md` — routing rules; which agent handles which work
- Multi-agent handoff workflow for deploying features end-to-end

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

| Command                         | What it does                                                      |
| ------------------------------- | ----------------------------------------------------------------- |
| `ccenv init`                    | Create `~/.ccenv/` with profiles, secrets, state, and Brief.md   |
| `ccenv apply <profile>`         | Wipe managed contents of `~/.claude/`, write profile + init memory |
| `ccenv switch <profile>`        | Same as apply; logs the previous → next switch                   |
| `ccenv status`                  | Show the active profile and list available profiles               |
| `ccenv chat`                    | Start interactive chat session with the active agent              |
| `ccenv memory init <agent>`     | Initialize Memory_Logs for an agent                              |
| `ccenv memory log <agent> "<summary>"` | Append a session entry to agent's Sessions/                |
| `ccenv memory show <agent>`     | Print the Context.md snapshot for an agent                       |
| `ccenv memory list`             | List all agents that have initialized memory                     |

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

## Agent Memory & Isolation

Each agent has **isolated, persistent memory** that survives across sessions.

### Memory Structure

When you apply a profile or init memory for an agent, ccenv creates:

```
~/.ccenv/agents/<agent>/Memory_Logs/
├── Context.md           # Quick startup snapshot (read this first)
├── Checkpoint.md        # Save/resume complex tasks
├── Lessons.md           # Patterns that worked, mistakes to avoid (append-only)
├── Preferences.md       # How the user likes things (append-only)
├── Sessions/            # One file per date: Session_YYYY-MM-DD.md
├── Notes/               # Knowledge captures, technical details
└── Archive/             # Compacted old sessions (for storage cleanup)
```

### Usage

**Initialize memory for a new agent:**
```bash
ccenv memory init devops
```

**Log a session after finishing work:**
```bash
ccenv memory log devops "Provisioned RDS instance with automated backups"
```

This appends to `Sessions/Session_YYYY-MM-DD.md`.

**View an agent's context snapshot:**
```bash
ccenv memory show devops
```

**List all agents with initialized memory:**
```bash
ccenv memory list
```

### Interactive Chat with Your Agent

Start an interactive chat session with the active agent immediately after applying a profile:

```bash
ccenv apply devops
```

This loads the agent's instructions + memory and opens an interactive prompt:

```
======================================================================
Agent: DEVOPS
Memory: /Users/maximus/.ccenv/agents/devops/Memory_Logs
======================================================================

Instructions:
----------------------------------------------------------------------
# DevOps Profile

You are pairing with a DevOps engineer doing infrastructure automation
and CI/CD operations.

... [full instructions] ...

----------------------------------------------------------------------

Chat Mode (type 'exit' or 'quit' to end session)
>>> Tell me how to provision an RDS instance
[Agent response here]
>>>
```

Your conversation is automatically logged to the agent's `Sessions/` when you exit.

### Key Rules

- **Memory is isolated:** When you switch agents, the new agent reads their own memory, **not** the previous agent's. No bleed.
- **Append-only:** Lessons and Preferences are append-only; never delete past entries.
- **Context is regenerated:** Context.md is refreshed on every scope change; it's a snapshot, not accumulated data.
- **Sessions accumulate:** One file per date; multiple entries within a day are appended.

## Team Coordination: Brief.md & Registry.md

**Brief.md** — Shared project dashboard:
```bash
cat Brief.md
```
Lists active agents, recent activity, blockers, handoff chains.

**Registry.md** — Agent routing and decision tree:
```bash
cat Registry.md
```
Maps work types to agents; documents handoff scenarios (e.g., "I need to deploy a feature").



## Tests

```bash
pip install -r requirements.txt
pytest -q
```

Tests use a fake `$HOME` (pytest's `tmp_path`) plus `unittest.mock` — they
never touch your real `~/.claude/` or `~/.ccenv/`.

## Multi-Agent Workflow Example

Deploy a feature from start to finish:

1. **Start with Frontend Agent** — Build the UI component
   ```bash
   ccenv apply frontend
   # ... Chat with frontend agent about component design ...
   # Type 'exit' to end session (auto-logs to memory)
   ```

2. **Switch to DevOps** — Provision any new infrastructure
   ```bash
   ccenv switch devops  # DevOps memory loads auto, Frontend memory is isolated
   # ... Chat with DevOps agent about infrastructure needs ...
   # Type 'exit' when done
   ```

3. **Switch to CI/CD** — Design the release
   ```bash
   ccenv switch cicd  # CI/CD memory loads, DevOps memory stays isolated
   # ... Chat with CI/CD architect about deployment strategy ...
   # Type 'exit' when done
   ```

4. **View Project Status**
   ```bash
   cat Brief.md      # See who did what, upcoming milestones
   cat Registry.md   # Understand which agent to switch to next
   ccenv memory list # See all agents' memory status
   ```

5. **Next Session** — Agents remember context
   ```bash
   ccenv switch devops
   ccenv chat
   # DevOps agent loads their Context.md, sessions, lessons, preferences
   # You pick up exactly where you left off
   ```

Each agent's memory is **completely isolated**—no context pollution when switching.



## Project layout

```
ccenv                      # the CLI (single file, executable)
profiles/                  # example profiles (copy into ~/.ccenv/profiles/)
  ├── devops/              # Infrastructure & CI/CD ops agent
  │   ├── profile.yaml
  │   ├── CLAUDE.md        # Agent instructions + memory loading
  │   ├── mcp.json         # Jenkins & GitHub MCP servers
  │   └── skills/
  │       ├── terraform-helper/
  │       └── jenkins-runner/
  ├── frontend/            # React/TypeScript UI development agent
  │   ├── profile.yaml
  │   ├── CLAUDE.md        # Agent instructions + memory loading
  │   ├── mcp.json         # Figma & Storybook MCP servers
  │   └── skills/
  │       ├── react-conventions/
  │       └── figma-bridge/
  └── cicd/                # CI/CD orchestration & release agent (NEW)
      ├── profile.yaml
      ├── CLAUDE.md        # Agent instructions + memory loading
      ├── mcp.json         # Jenkins & GitHub MCP servers
      └── skills/
          ├── pipeline-architect/
          └── release-manager/
Brief.md                   # Shared project dashboard (agents, activity, blockers)
Registry.md                # Agent routing rules (who handles what work)
tests/test_ccenv.py        # pytest suite
.github/workflows/ci.yml   # CI: runs pytest on every push
requirements.txt
design.md                  # the original writeup
```

## Built-In Agents

### **devops**
Infrastructure and CI/CD operations: Terraform, Jenkins, AWS provisioning, secrets management.
- Memory: `~/.ccenv/agents/devops/Memory_Logs/`
- Skills: `terraform-helper`, `jenkins-runner`

### **frontend**
React/TypeScript UI development with design-focused workflow.
- Memory: `~/.ccenv/agents/frontend/Memory_Logs/`
- Skills: `react-conventions`, `figma-bridge`

### **cicd**
CI/CD pipeline design and release orchestration. Coordinates multi-agent releases.
- Memory: `~/.ccenv/agents/cicd/Memory_Logs/`
- Skills: `pipeline-architect`, `release-manager`


