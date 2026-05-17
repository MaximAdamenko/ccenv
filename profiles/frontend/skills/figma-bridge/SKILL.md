---
name: figma-bridge
description: Translate Figma frames into React components.
---

# figma-bridge

Use when the user shares a Figma URL or asks to "implement this
design."

Workflow:
1. Inspect the frame via the Figma MCP server.
2. Emit a React component whose JSX hierarchy mirrors the frame's
   layer tree.
3. Map design tokens to Tailwind utility classes. Flag any nodes
   using raw hex colors that aren't in the design-system token list.
4. Reference Figma component names verbatim in the JSX so the diff
   to the design system is reviewable.
