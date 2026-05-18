---
name: release-manager
description: Manage releases, versioning, and deployment coordination across teams.
---

# release-manager

Use this skill when planning releases, managing version numbers, coordinating multi-team deployments, and defining release policies.

## Release Versioning
- **Semantic Versioning:** MAJOR.MINOR.PATCH (e.g., 2.5.3)
  - MAJOR: Breaking changes (database schema redesign, API incompatibility)
  - MINOR: Backward-compatible features (new endpoints, new columns with defaults)
  - PATCH: Bug fixes and security patches
- **Release tags:** Immutable in Git with annotations (date, author, release notes)
- **Changelog:** Keep a CHANGELOG.md documenting every release

## Release Checklist
Before shipping:
- [ ] All PR reviews completed and approved
- [ ] CI green on main (all tests passing)
- [ ] Security scan clean (no critical vulns)
- [ ] Staging deployment successful
- [ ] Smoke tests passing in staging
- [ ] Database migrations tested (if applicable)
- [ ] Notify stakeholders of deployment window
- [ ] Deploy to production (blue-green or canary)
- [ ] Monitor error rates and latency for 15min
- [ ] If bad metrics: auto-rollback or manual rollback
- [ ] Update service discovery / load balancer configs
- [ ] Document any manual steps taken
- [ ] Post-release retrospective (if any issues)

## Deployment Strategies
1. **Blue-Green:** Two production environments; route traffic after full deployment verification
2. **Canary:** Roll out to 5% → 25% → 50% → 100% with metrics gates between steps
3. **Rolling:** Gradually replace instances one at a time; fast rollback if health fails

## Coordination
- **Communicate release window:** Async chat, email, and Slack notifications
- **Frozen period:** 30min before → during → 15min after deployment; no new changes
- **Stakeholder SOP:** On-call engineer + product lead on call during production deployments
