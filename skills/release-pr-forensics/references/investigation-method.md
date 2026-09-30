# Release regression investigation method

A release boundary is evidence about **when** a change entered, not proof about **which** change caused a symptom.

Use a narrowing funnel:

1. Establish the exact good and bad refs.
2. Enumerate the actual commits between them.
3. Map commits to PRs while retaining direct commits.
4. Use metadata and changed paths to build a cheap shortlist.
5. Read full diffs only for shortlisted PRs.
6. Form a mechanism-level hypothesis.
7. Prefer a discriminating experiment: one-path replay, feature toggle, old/new predicate, targeted unit test, revert, cherry-pick or git bisect.

## Common false positives

- large PRs rank high merely because they touch many files;
- PR titles mention the symptom but code does not affect its path;
- generated files dominate the patch;
- refactors move code without semantic change;
- test PRs accompany an earlier production change;
- multiple PRs are coupled and only their interaction triggers the issue.

## Strong evidence

Strong evidence connects code and observation through a mechanism. Example:

- observation: only the first passage window shifts by one date;
- code change: strict `>` changed to `>=` in the first-passage boundary;
- experiment: replay one affected path under both predicates;
- result: the old predicate reproduces the good result and the new predicate reproduces the bad result.

That chain is far stronger than lexical similarity alone.
