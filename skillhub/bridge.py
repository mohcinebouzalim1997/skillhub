from __future__ import annotations

import json
import mimetypes
import secrets
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .catalog import iter_skills
from .installer import (
    available_agents,
    dependency_status,
    install_agent,
    install_pack,
    install_skill,
    install_skill_tree,
    install_stack,
    installed_agents,
    installed_skill_versions,
    uninstall_agent,
    uninstall_skill,
)
from .site import build_site
from .utils import SkillHubError, load_yaml


def _json_bytes(data: object) -> bytes:
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


def _status(root: Path) -> dict:
    available = {s.skill_id: str(s.metadata.get("version", "?")) for s in iter_skills(root)}
    installed = installed_skill_versions()
    skills = {}
    for skill_id, version in available.items():
        have = installed.get(skill_id)
        state = "not-installed" if have is None else ("current" if have == version else "update-available")
        skills[skill_id] = {"available": version, "installed": have, "state": state}
    agents_available = available_agents(root)
    agents_have = installed_agents()
    agents = {aid: {**info, "installed": aid in agents_have} for aid, info in agents_available.items()}
    stacks = {}
    for path in sorted((root / "stacks").glob("*.yaml")):
        data = load_yaml(path)
        sid = str(data.get("id") or path.stem)
        stack_skills = [str(v) for v in data.get("skills") or []]
        stack_agents = [str(v) for v in data.get("agents") or []]
        complete = all(skills.get(skill, {}).get("state") == "current" for skill in stack_skills) and all(
            agents.get(agent, {}).get("installed") for agent in stack_agents
        )
        stacks[sid] = {"name": data.get("name", sid), "installed": complete}
    return {"connected": True, "skills": skills, "agents": agents, "stacks": stacks}


def serve_marketplace(root: Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> int:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SkillHubError("The local control center may only bind to loopback addresses.")
    site_dir = build_site(root)
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        server_version = "SkillHubBridge/0.1"

        def _send_json(self, status: int, data: object) -> None:
            payload = _json_bytes(data)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def _authorized(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-SkillHub-Token", ""), token)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/session":
                self._send_json(HTTPStatus.OK, {"token": token, **_status(root)})
                return
            if parsed.path == "/api/status":
                self._send_json(HTTPStatus.OK, _status(root))
                return
            path = unquote(parsed.path).lstrip("/") or "index.html"
            target = (site_dir / path).resolve()
            try:
                target.relative_to(site_dir.resolve())
            except ValueError:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            if target.is_dir():
                target = target / "index.html"
            if not target.exists() or not target.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            data = target.read_bytes()
            content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid local bridge token"})
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > 32_768:
                self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large"})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON"})
                return
            path = urlparse(self.path).path
            try:
                if path == "/api/install-skill":
                    skill_id = str(body["skill"])
                    deps = dependency_status(root, skill_id)
                    if not deps["ok"]:
                        raise SkillHubError(f"Missing dependencies for {skill_id}: {json.dumps(deps)}")
                    out = install_skill_tree(root, skill_id, force=bool(body.get("force", False)))
                    result = {"ok": True, "paths": [str(p) for p in out]}
                elif path == "/api/update-skill":
                    out = install_skill_tree(root, str(body["skill"]), force=True)
                    result = {"ok": True, "paths": [str(p) for p in out]}
                elif path == "/api/uninstall-skill":
                    out = uninstall_skill(str(body["skill"]))
                    result = {"ok": True, "path": str(out)}
                elif path == "/api/install-pack":
                    out = install_pack(root, str(body["pack"]), force=bool(body.get("force", False)))
                    result = {"ok": True, "paths": [str(p) for p in out]}
                elif path == "/api/install-agent":
                    out = install_agent(root, str(body["agent"]), force=bool(body.get("force", False)))
                    result = {"ok": True, "path": str(out)}
                elif path == "/api/uninstall-agent":
                    out = uninstall_agent(str(body["agent"]))
                    result = {"ok": True, "path": str(out)}
                elif path == "/api/install-stack":
                    stack_id = str(body["stack"])
                    stack_path = root / "stacks" / f"{stack_id}.yaml"
                    if not stack_path.exists():
                        raise SkillHubError(f"Unknown stack: {stack_id}")
                    stack_data = load_yaml(stack_path)
                    missing = {sid: dependency_status(root, str(sid)) for sid in stack_data.get("skills") or []}
                    missing = {sid: state for sid, state in missing.items() if not state["ok"]}
                    if missing:
                        raise SkillHubError(f"Missing stack dependencies: {json.dumps(missing)}")
                    out = install_stack(root, stack_id, force=bool(body.get("force", False)))
                    result = {"ok": True, "skills": [str(p) for p in out["skills"]], "agents": [str(p) for p in out["agents"]]}
                else:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
                    return
                result["status"] = _status(root)
                self._send_json(HTTPStatus.OK, result)
            except (SkillHubError, KeyError, ValueError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[skillhub] {self.address_string()} - {fmt % args}")

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"SkillHub local control center: {url}")
    print("Bound to loopback only. Mutating API calls require an ephemeral same-origin session token.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSkillHub control center stopped.")
    finally:
        server.server_close()
    return 0
