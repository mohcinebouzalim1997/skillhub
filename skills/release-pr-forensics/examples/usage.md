# Usage examples

## Release branch

```text
Use /release-pr-forensics.
Repository: org/pricer
Release: release/26.10
Symptom: EEPE jumps only for MTF window 1.
First bad observation: 2026-09-22.
Find the smallest set of PRs worth testing and inspect only relevant patches first.
```

## Commit-to-commit

```text
Use /release-pr-forensics between commits 81e40f2 and a90a7cd.
The pricing batch became 22% slower. Prioritize runtime/concurrency/cache changes.
```

## Date window

```text
Use /release-pr-forensics for PRs merged between 2026-09-15 and 2026-09-22 on main.
The regression is a jump in an exposure metric. Preserve direct commits too.
```
