# Security model

SkillHub is designed for internal environments where skills may interact with proprietary source code or data.

## Non-negotiable controls

1. Keep the SkillHub repository private/internal.
2. **Verify the effective GitHub Pages access policy before deployment.** Do not infer site privacy only from repository privacy.
3. Never store credentials, tokens, passwords, certificates or production secrets in a skill.
4. Run GitHub API calls under the user's normal enterprise identity (`gh auth`).
5. Do not grant `allowed-tools: "*"` in v0.1.
6. Treat executable skill changes like code: review, CI and ownership.
7. Keep network and write permissions explicit in `skillhub.yaml`.
8. Prefer read-only retrieval for investigation skills; production mutation requires a separate review/security model.

The included validator contains lightweight secret-pattern detection. It is a guardrail, not a substitute for enterprise secret scanning, branch protection, code review or endpoint controls.

## Marketplace deployment

The MkDocs site is generated entirely from reviewed repository content and deployed as static files. It does not require a database or backend service. The site intentionally disables remote web fonts, and custom CSS/JavaScript is stored in the repository.

If GitHub Pages cannot meet the required internal visibility policy, build with `skillhub build-site` and publish `dist/site/` using an approved internal static-hosting mechanism instead.
