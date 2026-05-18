# Registry — Agent Routing and Handoff Rules

Use this to understand which agent is best suited for which work, and how to route tasks across the agent team.

---

## Agent Capabilities Matrix

### DevOps (`devops`)
**Expertise:**
- Terraform HCL & infrastructure-as-code
- Jenkins pipeline setup & debugging
- AWS/cloud provider configuration
- Secrets management (Vault, AWS Secrets Manager)
- Network topology & security groups
- Database provisioning & monitoring

**Handoff to Frontend:** When a deployment is ready and UI changes need staging/production verification  
**Handoff to CI/CD:** When infrastructure needs to be integrated into release pipelines

### Frontend (`frontend`)
**Expertise:**
- React/TypeScript component design
- Figma design → React translation
- Tailwind styling & design tokens
- Testing (React Testing Library)
- Component composition & state lifting
- User experience & accessibility

**Handoff to DevOps:** When components need to be deployed (DevOps sets up the infrastructure)  
**Handoff to CI/CD:** When release timing affects user-visible changes

### CI/CD (`cicd`)
**Expertise:**
- Pipeline design & orchestration
- Release strategy (blue-green, canary, rolling)
- Version management & semantic versioning
- Deployment gates & safety checks
- Multi-team coordination
- Artifact promotion across environments

**Handoff to DevOps:** For infrastructure pre-provisioning (new deployment stages)  
**Handoff to Frontend:** For UI feature freeze windows during releases

---

## Routing Decision Tree

**"I need to deploy infrastructure"**  
→ **DevOps** (Terraform, AWS provisioning)

**"I need to build a React component"**  
→ **Frontend** (Component architecture, design translation)

**"I need to design a deployment strategy"**  
→ **CI/CD** (Pipeline orchestration, release gates)

**"I need to connect a component to new infrastructure"**  
→ **Frontend** first (API integration), then **DevOps** (provision if needed)

**"I need to ship a feature with zero downtime"**  
→ **CI/CD** coordinates; **Frontend** handles code freeze; **DevOps** ensures infra ready

---

## Memory Rules

Each agent has **isolated** memory at `~/.ccenv/agents/<name>/Memory_Logs/`:

- **Sessions/** — Conversation history with outcomes
- **Lessons.md** — Patterns that worked, mistakes to avoid
- **Preferences.md** — How the user likes things done
- **Checkpoint.md** — Save/resume complex tasks
- **Context.md** — Quick startup snapshot

**Memory NEVER mixes across agents.** When you switch agents, the new agent reads their own memory, not the previous agent's.

---

## Session Logging

After completing work, log a session entry:

```bash
ccenv memory log devops "Provisioned new RDS instance with automated backups"
ccenv memory log frontend "Built UserCard component with design tokens"
ccenv memory log cicd "Designed canary deployment for 2.5.0 release"
```

This appends to `Sessions/Session_YYYY-MM-DD.md` and builds institutional knowledge.

---

## Team Coordination Checklist

**Before a major release:**
- [ ] **Frontend:** Features frozen, component testing complete
- [ ] **DevOps:** Infrastructure validated, secret rotation up to date
- [ ] **CI/CD:** Deployment pipeline tested, rollback plan documented
- [ ] **Brief.md:** Updated with release timeline and key changes
- [ ] **All agents:** Memory synced via `/memorize` command

---

## Common Handoff Scenarios

### Scenario 1: "Deploy a new feature to production"
1. **Frontend** builds & tests component (logs session)
2. **DevOps** provisions any new infrastructure (logs session)
3. **CI/CD** orchestrates release: staging → production (logs session)
4. Brief.md updated with completion

### Scenario 2: "Fix a bug in the deployment pipeline"
1. **CI/CD** diagnoses pipeline failure
2. If infra issue → handoff to **DevOps**
3. If component issue → handoff to **Frontend**
4. **CI/CD** updates pipeline config (logs session)

### Scenario 3: "Add a new third-party API to the project"
1. **Frontend** integrates API client in components
2. **DevOps** provisions API credentials, network access
3. **CI/CD** adds secrets to deployment pipeline
4. All log their sessions via `ccenv memory log <agent> <summary>`

