# SkillHub v0.1 skill contract

A skill is a directory under `skills/<id>/`.

Required:

- `SKILL.md` with `name` and `description` YAML frontmatter;
- `skillhub.yaml` with `schema_version`, `id`, `version`, `title`, `category`, `owner`, `status`.

Recommended for executable skills:

- `scripts/` with deterministic scripts;
- `references/` for domain knowledge;
- `tests/` for fixtures/scenarios.

## Naming

Skill IDs are lowercase letters/digits/hyphens, maximum 64 characters. Directory and `SKILL.md` name must match.

## Script contract

Prefer:

- explicit command-line arguments;
- structured JSON on stdout for success/failure summaries;
- JSON files for detailed machine-readable artifacts;
- Markdown summary for model/human progressive disclosure;
- non-zero exit codes on failure;
- no credentials in parameters unless there is no approved alternative;
- no `shell=True` when invoking external commands with user-controlled values.

## Safety

Network and filesystem requirements must be declared in `skillhub.yaml`. Production writes should default to false. Do not pre-approve unrestricted shell access.
