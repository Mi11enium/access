"""Публикация каталога dist/ на GitHub Pages (ветка gh-pages) через git.

Почему git, а не REST API: force-push одной ветки — это одна операция вместо
N запросов «создать/обновить файл», и она одинаково работает в Actions и на
Windows-машине без установленного gh.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

TOKEN_PLACEHOLDER = "***"


def _remote(repo: str, token: str) -> str:
    """owner/repo -> https URL с токеном; URL или локальный путь — как есть."""
    if "://" in repo:
        base = repo
    elif re.match(r"^[A-Za-z]:[\\/]", repo) or repo.startswith(("/", "./", "../")):
        return repo                       # локальный путь: проверка, зеркало на диск
    else:
        base = f"https://github.com/{repo}.git"
    if token and base.startswith("https://") and "@" not in base.split("/")[2]:
        base = base.replace("https://", f"https://x-access-token:{token}@", 1)
    return base


def _run(args: list[str], cwd: Path) -> tuple[int, str]:
    res = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=180)
    out = (res.stdout or "") + (res.stderr or "")
    return res.returncode, out.strip()


def publish(dist: Path, repo: str, branch: str = "gh-pages", token: str = "",
            message: str = "refresh") -> bool:
    """Выкладывает содержимое dist в ветку branch репозитория repo."""
    if not repo or ("/" not in repo and "\\" not in repo and "://" not in repo):
        print("[publish] не задан репозиторий (publish.repo или PUBLISH_REPO)", file=sys.stderr)
        return False
    if not (dist / "index.html").exists():
        print("[publish] в dist/ нет index.html", file=sys.stderr)
        return False

    url = _remote(repo, token)
    if url.startswith("https://") and "@" not in url.split("/")[2]:
        print("[publish] нет токена (GITHUB_TOKEN)", file=sys.stderr)
        return False
    steps = [
        ["git", "init", "-q"],
        ["git", "checkout", "-q", "-B", branch],
        ["git", "add", "-A"],
        ["git", "-c", "user.email=bot@users.noreply.github.com",
         "-c", "user.name=qrservice", "commit", "-q", "-m", message, "--allow-empty"],
        ["git", "push", "-q", "--force", url, f"{branch}:{branch}"],
    ]
    for cmd in steps:
        code, out = _run(cmd, dist)
        if code != 0:
            out = out.replace(token or "\x00", TOKEN_PLACEHOLDER)
            print(f"[publish] ошибка: {out[:400]}", file=sys.stderr)
            return False
    print(f"[publish] выложено: {repo} ({branch})", flush=True)
    return True
