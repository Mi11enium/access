"""Загрузка подписок и быстрый отсев заведомо мёртвых адресов."""
from __future__ import annotations

import socket
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from .nodes import Node, dedupe, parse_text

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def fetch_sub(url: str, name: str = "", timeout: int = 25, attempts: int = 2,
              limit: int = 400) -> tuple[list[Node], str]:
    """Тянет одну подписку. Возвращает (ноды, ошибка).

    Ходим всегда НАПРЯМУЮ (без системного прокси): иначе сервис, запущенный на
    машине с включённым VPN, качает подписки через собственный туннель.
    """
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    last: Exception | None = None
    for _ in range(max(1, attempts)):
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read(4 * 1024 * 1024)
            nodes = parse_text(raw.decode("utf-8", "ignore"), source=name or url)
            return nodes[:limit], ""
        except Exception as exc:               # noqa: BLE001
            last = exc
            time.sleep(1.0)
    return [], f"{type(last).__name__}: {last}"[:160]


def fetch_all(subs: list[dict], timeout: int = 25, attempts: int = 2,
              limit: int = 400) -> tuple[list[Node], dict[str, str]]:
    """Все включённые подписки параллельно."""
    active = [s for s in subs if s.get("enabled", True) and s.get("url")]
    errors: dict[str, str] = {}
    nodes: list[Node] = []
    if not active:
        return nodes, errors
    with ThreadPoolExecutor(max_workers=min(8, len(active))) as pool:
        futs = {pool.submit(fetch_sub, s["url"], s.get("name") or "", timeout,
                            attempts, limit): s for s in active}
        for fut in as_completed(futs):
            s = futs[fut]
            got, err = fut.result()
            name = s.get("name") or s.get("url")
            if err:
                errors[name] = err
                print(f"[subs] {name}: ОШИБКА {err}", flush=True)
            else:
                print(f"[subs] {name}: {len(got)} ссылок", flush=True)
            nodes.extend(got)
    return nodes, errors


def tcp_ping(host: str, port: int, timeout: float = 3.0) -> float | None:
    """TCP-connect до адреса ноды. Возвращает мс или None, если не отвечает.

    Дешёвый предфильтр: в бесплатных подписках половина адресов давно мертва,
    и гонять их через ядро — это минуты времени CI впустую.
    """
    t0 = time.perf_counter()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return (time.perf_counter() - t0) * 1000
    except (OSError, ValueError):
        return None


def prefilter(nodes: list[Node], timeout: float = 3.0, workers: int = 200,
              log_every: int = 200) -> list[Node]:
    """Оставляет только те адреса, где вообще открывается TCP-порт."""
    alive: list[Node] = []
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(nodes) or 1))) as pool:
        futs = {pool.submit(tcp_ping, n.address, n.port, timeout): n for n in nodes}
        for fut in as_completed(futs):
            node = futs[fut]
            ms = fut.result()
            done += 1
            if ms is not None:
                node.ping_ms = round(ms, 1)
                alive.append(node)
            if log_every and done % log_every == 0:
                print(f"[prefilter] {done}/{len(nodes)}, живых {len(alive)}", flush=True)
    print(f"[prefilter] проверено {len(nodes)}, TCP отвечает у {len(alive)}", flush=True)
    return alive


def pull(nodes: list[Node], kinds: list[str] | None = None) -> list[Node]:
    """Дедуп + отсев неподдерживаемых типов.

    `kinds` важен: в Xray 26 протокол ss (Shadowsocks) удалён, и ОДИН такой
    узел в конфиге валит запуск всего батча («unknown config id: ss»). Поэтому
    по умолчанию берём только те протоколы, которые текущее ядро умеет.
    """
    allow = {k.lower() for k in (kinds or [])}
    picked = [n for n in nodes if n.supported and (not allow or n.kind in allow)]
    return dedupe(picked)
