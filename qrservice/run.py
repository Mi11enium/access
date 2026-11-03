"""Точка входа: собрать → проверить → собрать страницу → опубликовать.

Запуск:
    python -m qrservice.run                 # собрать в dist/
    python -m qrservice.run --serve 8099    # + локальный сервер для просмотра
    python -m qrservice.run --publish       # + выложить на GitHub Pages
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import secrets
import sys
import time
from pathlib import Path

from . import core, probe, site, subs

ROOT = Path(__file__).resolve().parent.parent
STATE_KEEP_DAYS = 7


def load_cfg(path: Path) -> dict:
    cfg = json.loads(path.read_text("utf-8"))
    return cfg


def _load_dotenv() -> None:
    """Читает .env.local / .env из корня проекта (если есть).

    Нужно для локального запуска по расписанию: токен и адреса лежат в файле,
    который не попадает в репозиторий, а не в командной строке.
    """
    for name in (".env.local", ".env"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text("utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:]
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def env_overrides(cfg: dict) -> dict:
    """Секреты и адреса удобнее держать в окружении, а не в публичном конфиге."""
    site_cfg = cfg.setdefault("site", {})
    pub = cfg.setdefault("publish", {})
    if os.environ.get("SITE_SLUG"):
        site_cfg["slug"] = os.environ["SITE_SLUG"].strip()
    if os.environ.get("SITE_TITLE"):
        site_cfg["title"] = os.environ["SITE_TITLE"].strip()
    if os.environ.get("PUBLISH_REPO"):
        pub["repo"] = os.environ["PUBLISH_REPO"].strip()
    if os.environ.get("PAGES_URL"):
        pub["pages_url"] = os.environ["PAGES_URL"].strip().rstrip("/")
    if os.environ.get("PUBLISH_BRANCH"):
        pub["branch"] = os.environ["PUBLISH_BRANCH"].strip()
    if not site_cfg.get("slug"):
        site_cfg["slug"] = secrets.token_hex(8)
        print(f"[cfg] slug не задан — сгенерирован разовый: {site_cfg['slug']}", flush=True)
    return cfg


def load_state(out_root: Path, slug: str, pages_url: str) -> dict:
    """История проверок: локальный файл, иначе — прошлый state.json с сайта."""
    local = out_root / slug / "state.json"
    if local.exists():
        try:
            return json.loads(local.read_text("utf-8"))
        except Exception:                      # noqa: BLE001
            pass
    if pages_url:
        import urllib.request
        url = f"{pages_url}/{slug}/state.json"
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url, timeout=15) as resp:
                return json.loads(resp.read(2 * 1024 * 1024).decode("utf-8"))
        except Exception as exc:               # noqa: BLE001
            print(f"[state] история недоступна ({exc}) — считаем с нуля", flush=True)
    return {"updated": 0, "runs": 0, "nodes": {}}


def update_state(state: dict, checked: list, now: float) -> dict:
    """Обновляет аптайм: сколько последних проверок нода отработала."""
    nodes = dict(state.get("nodes") or {})
    alive_ids = set()
    for n in checked:
        nodes[n.ident] = {"ok": int(nodes.get(n.ident, {}).get("ok", 0)) + (1 if n.ok else 0),
                          "total": int(nodes.get(n.ident, {}).get("total", 0)) + 1,
                          "last_ok": now if n.ok else nodes.get(n.ident, {}).get("last_ok", 0),
                          "ping": round(n.ping_ms, 1),
                          "name": n.label, "kind": n.kind,
                          "link": n.link, "source": n.source}
        if n.ok:
            alive_ids.add(n.ident)
    horizon = now - STATE_KEEP_DAYS * 86400
    nodes = {k: v for k, v in nodes.items()
             if float(v.get("last_ok") or 0) >= horizon or k in alive_ids}
    if len(nodes) > 800:
        keep = sorted(nodes.items(), key=lambda kv: -(float(kv[1].get("last_ok") or 0)))[:800]
        nodes = dict(keep)
    return {"updated": int(now), "runs": int(state.get("runs") or 0) + 1, "nodes": nodes}


def fallback_nodes(state: dict, hours: float = 6.0) -> list[dict]:
    """Последние живые ноды — когда текущая проверка не нашла ничего."""
    horizon = time.time() - hours * 3600
    out = []
    for ident, st in (state.get("nodes") or {}).items():
        if float(st.get("last_ok") or 0) < horizon or not st.get("link"):
            continue
        out.append({"id": ident, "kind": st.get("kind") or "vless",
                    "name": st.get("name") or ident, "ping": st.get("ping") or 0,
                    "link": st["link"], "source": st.get("source") or "",
                    "security": "", "network": ""})
    return out


def origin_text(cfg: dict) -> str:
    if os.environ.get("GITHUB_ACTIONS"):
        return "Проверено из GitHub Actions (зарубежный дата-центр)"
    return f"Проверено локально ({platform.system()} {platform.release()})"


def serve(directory: Path, port: int) -> None:
    import functools
    import http.server

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    with http.server.ThreadingHTTPServer(("0.0.0.0", port), handler) as httpd:
        print(f"[serve] http://127.0.0.1:{port}/", flush=True)
        httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Проверка серверов и генерация страницы с QR-кодами")
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--publish", action="store_true", help="выложить dist на GitHub Pages")
    ap.add_argument("--serve", type=int, default=0, help="поднять локальный сервер на порту")
    ap.add_argument("--limit", type=int, default=0, help="проверить не больше N нод (для отладки)")
    ap.add_argument("--no-speed", action="store_true", help="без замера скорости")
    args = ap.parse_args(argv)

    _load_dotenv()
    cfg = env_overrides(load_cfg(Path(args.config)))
    out_root = Path(args.out)
    site_cfg = cfg.get("site", {}) or {}
    pub_cfg = cfg.get("publish", {}) or {}
    slug = re.sub(r"[^A-Za-z0-9_-]", "", str(site_cfg.get("slug") or "")) or secrets.token_hex(8)
    pages_url = str(pub_cfg.get("pages_url") or "").rstrip("/")
    sub_url = f"{pages_url}/{slug}/sub.txt" if pages_url else ""

    exe = core.find_xray(str(cfg.get("xray") or "") or None)
    if not exe:
        print("[xray] ядро не найдено: положите бинарь в ./bin или задайте XRAY_BIN", file=sys.stderr)
        return 2
    print(f"[xray] {exe} — {core.xray_version(exe)}", flush=True)

    t0 = time.time()
    fetch_cfg = cfg.get("fetch", {}) or {}
    print(f"[start] подписок: {len(cfg.get('subscriptions') or [])}", flush=True)
    raw_nodes, errors = subs.fetch_all(
        cfg.get("subscriptions") or [],
        timeout=int(fetch_cfg.get("timeout", 25)),
        attempts=int(fetch_cfg.get("attempts", 2)),
        limit=int(fetch_cfg.get("max_per_sub", 400)),
    )
    unique = subs.pull(raw_nodes, (cfg.get("probe") or {}).get("kinds"))
    print(f"[start] ссылок {len(raw_nodes)}, уникальных рабочих конфигураций {len(unique)}", flush=True)
    if not unique:
        print("[fail] ни одной конфигурации из подписок — публикую прошлое состояние", file=sys.stderr)

    probe_cfg = cfg.get("probe", {}) or {}
    tcp_alive = subs.prefilter(unique,
                               timeout=float(probe_cfg.get("tcp_timeout", 3)),
                               workers=int(probe_cfg.get("tcp_workers", 200)))
    if args.limit:
        tcp_alive = tcp_alive[: args.limit]
    print(f"[start] после TCP-фильтра: {len(tcp_alive)}", flush=True)

    probe.measure(tcp_alive, probe_cfg, exe)
    if not args.no_speed:
        probe.measure_speed(tcp_alive, probe_cfg, exe)

    now = time.time()
    state = load_state(out_root, slug, pages_url)
    state = update_state(state, tcp_alive, now)

    alive = sorted([n for n in tcp_alive if n.ok], key=lambda n: n.ping_ms)
    public = [n.to_public() for n in alive]
    for n in public:
        src = next((x for x in tcp_alive if x.ident == n["id"]), None)
        if src is not None:
            n["security"] = {"tls": "TLS", "reality": "Reality"}.get(src.security, "")
            n["network"] = src.network

    stale = False
    max_nodes = int(site_cfg.get("max_nodes", 40))
    if not public:
        public = fallback_nodes(state)[:max_nodes]
        stale = bool(public)
    public = public[:max_nodes]

    info = site.build_site(public, state, cfg, out_root, slug, sub_url,
                           origin_text(cfg), stale=stale)
    print(f"[site] {info['page']} — серверов на странице: {info['count']} "
          f"({', '.join(f'{k}:{v}' for k, v in info['kinds'].items()) or 'нет'})", flush=True)
    if errors:
        for name, err in errors.items():
            print(f"[site] подписка «{name}» недоступна: {err}", flush=True)
    print(f"[done] {time.time() - t0:.0f} c", flush=True)

    if slug and pages_url:
        print(f"[site] адрес: {pages_url}/{slug}/", flush=True)

    if args.publish or os.environ.get("PUBLISH") == "1":
        from . import publish as pub
        ok = pub.publish(out_root, str(pub_cfg.get("repo") or ""),
                         str(pub_cfg.get("branch") or "gh-pages"),
                         os.environ.get("GITHUB_TOKEN", ""))
        if not ok:
            return 3

    if args.serve:
        serve(out_root, args.serve)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
