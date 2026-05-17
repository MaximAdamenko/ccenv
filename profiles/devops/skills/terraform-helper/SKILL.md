---
name: terraform-helper
description: Helpers for writing and reviewing Terraform modules.
---

# terraform-helper

Use this skill whenever the user asks about Terraform, HCL syntax,
provider configuration, state management, or refactoring `.tf` files
into reusable modules.

Conventions:
- Emit `terraform fmt`-compatible output.
- Flag resources missing `lifecycle { prevent_destroy = true }` for
  anything tagged `critical = "true"`.
- Prefer remote state (S3 + DynamoDB lock or Terraform Cloud) over
  local state for anything beyond a throwaway sandbox.
- Pin provider versions (`~>`) — never leave them unbounded.
