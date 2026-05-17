---
name: jenkins-runner
description: Author, debug, and review Jenkins pipelines.
---

# jenkins-runner

Trigger this skill for `Jenkinsfile` work and CI debugging.

Conventions:
- Declarative pipeline syntax by default; only drop to scripted when
  the user explicitly needs Groovy control flow.
- Use `agent { label '...' }` rather than `agent any`.
- Wrap any credential use in `withCredentials([...])`; never echo
  secrets in `sh` steps.
- Surface `post { failure { ... } }` blocks when adding new stages.
