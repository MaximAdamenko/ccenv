---
name: pipeline-architect
description: Design, review, and optimize CI/CD pipelines for reproducibility and safety.
---

# pipeline-architect

Use this skill when designing or reviewing CI/CD pipelines, deployment strategies, and release automation.

## Principles
- **Declarative over scripted:** Use Jenkins Declarative syntax or GitHub Actions YAML for clarity
- **Immutable artifacts:** Build once, tag immutably, deploy the same artifact across stages
- **Staged progression:** dev → staging → production with automatic gates on tests, manual gates on approval
- **Fast feedback:** Run critical tests early; fail fast to unblock developers
- **Observability:** Log all deployments to a central audit trail; enable instant rollback

## Common Patterns
1. **Build stage:** Compile, unit tests, artifact tagging
2. **Test stage:** Integration tests, security scans (SAST/DAST), coverage gates
3. **Deploy-to-staging:** Automated with smoke tests; manual approval before production
4. **Deploy-to-production:** Blue-green or canary; monitor health checks; auto-rollback on failure
5. **Post-deploy:** Update service discovery, run integration tests, notify team

## Anti-patterns to Avoid
- Rebuilding code in each stage (pull artifact from registry instead)
- Manual approval without a formal gate (approval must be in the pipeline config)
- Hardcoded credentials in pipeline files (inject via secrets manager)
- Merging directly to main without CI green (require branch protection rules)
