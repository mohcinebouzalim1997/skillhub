# Security model

SkillHub treats executable AI capabilities as software supply-chain artifacts.

1. **Least privilege** — each skill declares GitHub/filesystem/network needs.
2. **No stored GitHub secret** — release retrieval uses the workstation's authenticated `gh` identity.
3. **No target-repo mutation** — collection/inspection are read-only against GitHub; analysis artifacts are written locally.
4. **No `shell=True`** in platform execution paths.
5. **Progressive disclosure** — large full diffs are not pulled into AI context by default.
6. **Causality discipline** — ranking scores mean retrieval relevance, not probability of guilt.
7. **Local control server binds only to loopback** and mutations require an ephemeral same-origin token.
8. **Static Pages cannot install software** — install/update buttons activate only in the local control-center mode.
9. **Skills are personally installed** — product repositories stay clean.
10. **Secrets scanner** — repository validation checks common token/private-key signatures in small text artifacts.

Before publishing the Pages site, verify your enterprise's effective Pages visibility; repository privacy alone must not be assumed to imply Pages privacy.
