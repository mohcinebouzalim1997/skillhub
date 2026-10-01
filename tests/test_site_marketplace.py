from pathlib import Path
import re
import yaml

from skillhub.site import prepare_site_sources

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def _assert_local_href(source: Path, href: str) -> None:
    if href.startswith(("http://", "https://", "mailto:", "#")):
        return
    clean = href.split("#", 1)[0].split("?", 1)[0]
    if not clean:
        return
    target = (source.parent / clean).resolve()
    if clean.endswith("/"):
        target = target / "index.md"
    elif not target.suffix:
        target = target / "index.md"
    assert target.exists(), f"broken local href in {source}: {href} -> {target}"


def test_mkdocs_config_and_generated_marketplace_links():
    cfg = yaml.safe_load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    assert cfg["theme"]["name"] == "material"
    assert cfg["strict"] is True
    assert "search" in [p if isinstance(p, str) else next(iter(p)) for p in cfg["plugins"]]

    data = prepare_site_sources(ROOT)
    assert len(data["skills"]) == 7
    assert "Copy install" in (DOCS / "marketplace" / "index.md").read_text(encoding="utf-8")

    for source in [DOCS / "index.md", DOCS / "marketplace" / "index.md"]:
        text = source.read_text(encoding="utf-8")
        for href in re.findall(r'href="([^"]+)"', text):
            _assert_local_href(source, href)


def test_registry_excludes_python_bytecode():
    data = prepare_site_sources(ROOT)
    paths = [f["path"] for skill in data["skills"] for f in skill["files"]]
    assert not any("__pycache__" in path or path.endswith((".pyc", ".pyo")) for path in paths)
