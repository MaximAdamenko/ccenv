---
name: react-conventions
description: House conventions for React + TypeScript components.
---

# react-conventions

Apply when writing or reviewing React/TSX.

Conventions:
- Function components only; no class components.
- Type props explicitly with an interface — do not use `React.FC`.
- Lift state up rather than threading contexts everywhere; prefer
  composition over render props.
- Co-locate tests in `*.test.tsx`; use React Testing Library.
- For server state, reach for `@tanstack/react-query` before Redux.
