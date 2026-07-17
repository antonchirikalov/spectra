#!/usr/bin/env python3
"""Publish Markdown documents to Confluence Server/Data Center.

This script is intentionally self-contained for Windows publishing workflows.
It converts Markdown to Confluence storage XHTML via Pandoc, creates or updates
a page, and uploads local PNG/PDF attachments using Bearer PAT auth.
"""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

try:
    import httpx
except ImportError as exc:  # pragma: no cover - runtime guard
    raise SystemExit("httpx is required: pip install httpx") from exc


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _load_claude_settings() -> None:
    settings = Path(os.path.expanduser("~/.claude/settings.json"))
    if not settings.exists():
        return
    try:
        data = json.loads(settings.read_text(encoding="utf-8-sig"))
    except Exception:
        return
    for cfg in data.get("mcpServers", {}).values():
        env = (cfg or {}).get("env", {})
        if not isinstance(env, dict):
            continue
        if env.get("CONFLUENCE_PERSONAL_TOKEN") or env.get("CONFLUENCE_TOKEN"):
            for key in ("CONFLUENCE_URL", "CONFLUENCE_PERSONAL_TOKEN", "CONFLUENCE_TOKEN"):
                if env.get(key) and key not in os.environ:
                    os.environ[key] = env[key]
            return


def load_credentials() -> tuple[str, str]:
    _load_claude_settings()
    _load_dotenv(_repo_root() / ".env")
    url = os.environ.get("CONFLUENCE_URL", "https://confluence.scnsoft.com").rstrip("/")
    token = os.environ.get("CONFLUENCE_PERSONAL_TOKEN") or os.environ.get("CONFLUENCE_TOKEN")
    if not token:
        raise SystemExit("Set CONFLUENCE_PERSONAL_TOKEN/CONFLUENCE_TOKEN or configure ~/.claude/settings.json")
    return url, token


def first_h1(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return re.sub(r"[`*_]", "", m.group(1)).strip()
    return fallback


def pandoc_html(markdown_path: Path, resource_paths: list[Path]) -> str:
    cmd = [
        "pandoc",
        "-f",
        "markdown-citations",
        "-t",
        "html",
        "--wrap=none",
        str(markdown_path),
    ]
    if resource_paths:
        cmd.insert(-1, "--resource-path=" + os.pathsep.join(str(p) for p in resource_paths))
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or "pandoc failed")
    return proc.stdout


def convert_images_to_confluence(html_text: str) -> str:
    # Pandoc preserves raw HTML from Markdown tables.  Confluence's storage
    # parser is XML-based, so bare HTML line breaks such as ``<br>`` must be
    # normalized to self-closing XHTML before the body is submitted.
    html_text = re.sub(r"<br\s*>", "<br />", html_text, flags=re.IGNORECASE)

    def image_markup(attrs: str) -> str:
        src_m = re.search(r'\bsrc="([^"]+)"', attrs)
        alt_m = re.search(r'\balt="([^"]*)"', attrs)
        if not src_m:
            return ""
        filename = Path(html.unescape(src_m.group(1))).name
        alt = html.unescape(alt_m.group(1)) if alt_m else filename
        return (
            f'<ac:image ac:alt="{html.escape(alt, quote=True)}" ac:width="800">'
            f'<ri:attachment ri:filename="{html.escape(filename, quote=True)}" />'
            f'</ac:image>'
        )

    def figure_repl(match: re.Match[str]) -> str:
        image = image_markup(match.group(1))
        if not image:
            return match.group(0)
        caption = match.group(2)
        return f"<p>{image}</p>\n<p><em>{caption}</em></p>"

    def repl(match: re.Match[str]) -> str:
        image = image_markup(match.group(1))
        return image or match.group(0)

    # Pandoc renders consecutive markdown image + italic caption as a single
    # paragraph: <p><img ... /> <em>Fig. N...</em></p>. Confluence storage does
    # not reliably render inline text after an ac:image macro, so split it into
    # an image paragraph and a visible caption paragraph.
    html_text = re.sub(
        r"<p>\s*<img\s+([^>]*?)\s*/?>\s*<em>(.*?)</em>\s*</p>",
        figure_repl,
        html_text,
        flags=re.DOTALL,
    )
    return re.sub(r"<img\s+([^>]*?)\s*/?>", repl, html_text)


def add_toc(body: str) -> str:
    toc = '<ac:structured-macro ac:name="toc"><ac:parameter ac:name="maxLevel">3</ac:parameter></ac:structured-macro>'
    return toc + "\n" + body


class ConfluenceClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=120,
            follow_redirects=True,
        )

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def get_page(self, page_id: str) -> dict:
        r = self.client.get(self._url(f"/rest/api/content/{page_id}"), params={"expand": "version,space,_links"})
        r.raise_for_status()
        return r.json()

    def find_child_by_title(self, parent_id: str, title: str) -> dict | None:
        start = 0
        while True:
            r = self.client.get(
                self._url(f"/rest/api/content/{parent_id}/child/page"),
                params={"limit": 100, "start": start, "expand": "version,space,_links"},
            )
            r.raise_for_status()
            data = r.json()
            for item in data.get("results", []):
                if item.get("title") == title:
                    return item
            size = len(data.get("results", []))
            if size == 0 or not data.get("_links", {}).get("next"):
                return None
            start += size

    def create_page(self, space: str, parent_id: str, title: str, body: str) -> dict:
        payload = {
            "type": "page",
            "title": title,
            "space": {"key": space},
            "ancestors": [{"id": parent_id}],
            "body": {"storage": {"value": body, "representation": "storage"}},
        }
        r = self.client.post(self._url("/rest/api/content"), json=payload, headers={"Content-Type": "application/json"})
        r.raise_for_status()
        return r.json()

    def update_page(self, page_id: str, title: str, body: str) -> dict:
        page = self.get_page(page_id)
        version = int(page["version"]["number"]) + 1
        space = page["space"]["key"]
        payload = {
            "id": page_id,
            "type": "page",
            "title": title,
            "space": {"key": space},
            "version": {"number": version, "minorEdit": False},
            "body": {"storage": {"value": body, "representation": "storage"}},
        }
        r = self.client.put(self._url(f"/rest/api/content/{page_id}"), json=payload, headers={"Content-Type": "application/json"})
        r.raise_for_status()
        return r.json()

    def upload_attachment(self, page_id: str, path: Path) -> dict:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        existing = self.find_attachment(page_id, path.name)
        if existing:
            return self.update_attachment_data(page_id, existing["id"], path, mime)

        with path.open("rb") as f:
            files = {"file": (path.name, f, mime)}
            r = self.client.post(
                self._url(f"/rest/api/content/{page_id}/child/attachment"),
                headers={"X-Atlassian-Token": "no-check"},
                files=files,
            )
        if r.status_code in {400, 409}:
            existing = self.find_attachment(page_id, path.name)
            if existing:
                return self.update_attachment_data(page_id, existing["id"], path, mime)
        r.raise_for_status()
        return r.json()

    def find_attachment(self, page_id: str, filename: str) -> dict | None:
        r = self.client.get(
            self._url(f"/rest/api/content/{page_id}/child/attachment"),
            params={"filename": filename, "expand": "version"},
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0] if results else None

    def update_attachment_data(self, page_id: str, attachment_id: str, path: Path, mime: str) -> dict:
        with path.open("rb") as f:
            files = {"file": (path.name, f, mime)}
            r = self.client.post(
                self._url(f"/rest/api/content/{page_id}/child/attachment/{attachment_id}/data"),
                headers={"X-Atlassian-Token": "no-check"},
                files=files,
            )
        r.raise_for_status()
        return r.json()

    def web_url(self, page: dict) -> str:
        links = page.get("_links", {})
        base = links.get("base") or self.base_url
        webui = links.get("webui") or f"/pages/viewpage.action?pageId={page.get('id')}"
        return base.rstrip("/") + webui


def existing_files(paths: Iterable[str]) -> list[Path]:
    result = []
    for item in paths:
        path = Path(item).expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"Attachment not found: {path}")
        result.append(path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish Markdown to Confluence Server/DC")
    parser.add_argument("--draft", required=True, help="Markdown document path")
    parser.add_argument("--parent-id", help="Parent page ID for create/upsert")
    parser.add_argument("--space", required=True, help="Confluence space key")
    parser.add_argument("--title", help="Page title; default is first H1")
    parser.add_argument("--update", help="Existing page ID to update")
    parser.add_argument("--illustrations", help="Folder with PNG images to upload")
    parser.add_argument("--attachment", action="append", default=[], help="Extra file attachment; repeatable")
    parser.add_argument("--no-toc", action="store_true", help="Do not prepend Confluence TOC macro")
    parser.add_argument("--force-new", action="store_true", help="Always create a new page even if a child with the same title exists")
    args = parser.parse_args()

    draft = Path(args.draft).expanduser().resolve()
    if not draft.exists():
        raise SystemExit(f"Draft not found: {draft}")
    if not args.update and not args.parent_id:
        raise SystemExit("Provide --update or --parent-id")

    markdown = draft.read_text(encoding="utf-8")
    title = args.title or first_h1(markdown, draft.stem)
    resource_paths = [draft.parent]
    illustration_paths: list[Path] = []
    if args.illustrations:
        illustrations_dir = Path(args.illustrations).expanduser().resolve()
        if not illustrations_dir.exists():
            raise SystemExit(f"Illustrations folder not found: {illustrations_dir}")
        resource_paths.append(illustrations_dir)
        illustration_paths = sorted(illustrations_dir.glob("*.png"))
    extra_attachments = existing_files(args.attachment)

    body = convert_images_to_confluence(pandoc_html(draft, resource_paths))
    if not args.no_toc:
        body = add_toc(body)

    base_url, token = load_credentials()
    confluence = ConfluenceClient(base_url, token)

    if args.update:
        page = confluence.update_page(args.update, title, body)
        action = "updated"
    elif args.force_new:
        confluence.get_page(args.parent_id)  # fail early on invalid parent/auth
        page = confluence.create_page(args.space, args.parent_id, title, body)
        action = "created"
    else:
        existing = confluence.find_child_by_title(args.parent_id, title)
        if existing:
            page = confluence.update_page(existing["id"], title, body)
            action = "updated"
        else:
            confluence.get_page(args.parent_id)  # fail early on invalid parent/auth
            page = confluence.create_page(args.space, args.parent_id, title, body)
            action = "created"

    uploads = 0
    for path in [*illustration_paths, *extra_attachments]:
        confluence.upload_attachment(page["id"], path)
        uploads += 1

    final_page = confluence.get_page(page["id"])
    print(json.dumps({
        "status": action,
        "id": final_page["id"],
        "title": final_page["title"],
        "version": final_page["version"]["number"],
        "url": confluence.web_url(final_page),
        "attachments_uploaded": uploads,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
