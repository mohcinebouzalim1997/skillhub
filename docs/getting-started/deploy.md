# Deploy to GitHub Pages

1. Push SkillHub to its own GitHub repository.
2. Open **Settings → Pages**.
3. Select **GitHub Actions** as the publishing source.
4. Confirm enterprise Pages visibility/access control before publishing internal Quant content.
5. Push `main`.

The workflow validates the hub, generates registry-derived pages, runs `mkdocs build --strict`, uploads the Pages artifact and deploys it.

## Local static preview

```powershell
skillhub serve-site
```

## Local interactive control center

```powershell
skillhub marketplace --open
```

The interactive mode is local only; GitHub Pages remains a static discoverability layer.
