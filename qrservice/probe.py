"""Проверка нод реальным трафиком: curl через socks-inbound ядра Xray.

TCP-порт может быть открыт, а UUID/ключ REALITY — отозваны: клиент такой сервер
«подключит», но трафика не будет. Поэтому живой считается только та нода, через
которую реально прошёл HTTP-запрос к generate_204.
"""
from __future__ import annotations

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .core import Xray
from .nodes import Node
from .xraycfg import batch_config, free_block

IS_WIN = os.name == "nt"
DEVNULL = "NUL" if IS_WIN else "/dev/null"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) qrservice/1.0"
_CLEAN_ENV = {k: v for k, v in os.environ.items()
              if k.lower() not in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")}
_CREATE_NO_WINDOW = 0x08000000 if IS_WIN else 0


def _curl(port: int | None, url: str, timeout: float,
          fmt: str = "%{http_code};%{time_starttransfer}") -> tuple[bool, int, float, str]:
    cmd = ["curl", "-sS", "-o", DEVNULL]
    if port is not None:
        cmd += ["-x", f"socks5h://127.0.0.1:{int(port)}"]
    cmd += ["--max-time", str(timeout), "--connect-timeout", str(max(2, int(timeout))),
            "-A", UA, "-w", fmt, url]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 6,
                             env=_CLEAN_ENV, creationflags=_CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return False, 0, 0.0, "таймаут"
    except Exception as exc:                   # noqa: BLE001
        return False, 0, 0.0, f"{type(exc).__name__}: {exc}"[:80]

    parts = (res.stdout or "").strip().splitlines()
    code, ttfb = 0, 0.0
    if parts:
        chunk = parts[-1].split(";")
        try:
            code = int(float(chunk[0] or 0))
            ttfb = float(chunk[1] or 0)
        except (ValueError, IndexError):
            pass
    if res.returncode != 0:
        err = (res.stderr or "").strip().replace("\n", " ")[:100] or f"curl {res.returncode}"
        return False, code, ttfb, err
    return code in (200, 204), code, ttfb, ""


def _probe_node(node: Node, port: int, urls: list[str], timeout: float) -> None:
    best = 0.0
    last_err = "нет ответа"
    for url in urls:
        ok, code, ttfb, err = _curl(port, url, timeout)
        if ok:
            best = ttfb * 1000 if ttfb else timeout * 1000
            last_err = ""
            break
        last_err = err or f"http {code}"
    node.ok = bool(best)
    node.error = last_err
    node.ping_ms = round(best, 1) if best else 0.0


def _run_chunk(nodes: list[Node], base: int, span: int, exe: str,
               urls: list[str], timeout: float, workers: int,
               depth: int = 0) -> tuple[int, int]:
    """Один батч: поднять ядро на N inbound'ов, прогнать замеры, погасить.

    Если ядро не поднялось — значит, один из узлов содержит параметры, которые
    оно отвергает (в публичных подписках это обычное дело). Делим батч пополам,
    пока не останутся только валидные узлы.
    """
    port = free_block(base, span, len(nodes))
    if port is None:
        for n in nodes:
            n.error = "нет свободных портов"
        return 0, len(nodes)

    proc = Xray(exe)
    if not proc.start(batch_config(nodes, port)):
        for n in nodes:
            n.error = "ядро не запустилось"
        return 0, len(nodes)
    try:
        ready = proc.wait_ports([port + i for i in range(len(nodes))], timeout=15)
        if not ready:
            tail = proc.tail(4)
            proc.stop()
            if len(nodes) == 1:
                nodes[0].error = f"конфиг отвергнут ядром ({tail})"[:160]
                return 0, 1
            if depth >= 6:
                for n in nodes:
                    n.error = "ядро не приняло батч"
                return 0, len(nodes)
            mid = len(nodes) // 2
            a_ok, _ = _run_chunk(nodes[:mid], base, span, exe, urls, timeout, workers, depth + 1)
            b_ok, _ = _run_chunk(nodes[mid:], base, span, exe, urls, timeout, workers, depth + 1)
            return a_ok + b_ok, len(nodes)
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(nodes)))) as pool:
            futs = [pool.submit(_probe_node, n, port + i, urls, timeout)
                    for i, n in enumerate(nodes)]
            for f in as_completed(futs):
                try:
                    f.result()
                except Exception:              # noqa: BLE001
                    pass
    finally:
        proc.stop()
    alive = sum(1 for n in nodes if n.ok)
    return alive, len(nodes)


def measure(nodes: list[Node], cfg: dict, exe: str) -> int:
    """Прогоняет все ноды батчами (в несколько полос). Возвращает число живых."""
    if not nodes:
        return 0
    batch = max(1, int(cfg.get("batch", 48)))
    lanes = max(1, int(cfg.get("lanes", 1)))
    base = int(cfg.get("port_base", 23100))
    span = max(batch, int(cfg.get("port_span", 4096)))
    urls = list(cfg.get("ping_urls") or ["https://www.gstatic.com/generate_204"])
    timeout = float(cfg.get("ping_timeout", 7))
    workers = max(1, int(cfg.get("workers", 48)))

    lanes = min(lanes, len(nodes))
    lane_span = max(batch, span // lanes)
    shards = [nodes[i::lanes] for i in range(lanes)]
    print(f"[probe] нод {len(nodes)}, полос {lanes}, батч {batch}", flush=True)

    def lane(idx: int, shard: list[Node]) -> int:
        alive = 0
        start_base = base + idx * lane_span
        for i in range(0, len(shard), batch):
            chunk = shard[i:i + batch]
            got, _ = _run_chunk(chunk, start_base, lane_span, exe, urls, timeout, workers)
            alive += got
            print(f"[probe] полоса {idx + 1}: {min(i + batch, len(shard))}/{len(shard)} "
                  f"проверено, живых в полосе {alive}", flush=True)
        return alive

    total = 0
    with ThreadPoolExecutor(max_workers=lanes) as ex:
        futs = [ex.submit(lane, i, s) for i, s in enumerate(shards)]
        for f in as_completed(futs):
            try:
                total += f.result()
            except Exception as exc:           # noqa: BLE001
                print(f"[probe] полоса упала: {exc}", flush=True)
    print(f"[probe] живых нод: {total} из {len(nodes)}", flush=True)
    return total


def measure_speed(nodes: list[Node], cfg: dict, exe: str) -> None:
    """Замер скорости у лучших нод (Мбит/с, скачивание speed_url)."""
    top = int(cfg.get("speed_top", 0) or 0)
    if top <= 0:
        return
    pool_nodes = sorted([n for n in nodes if n.ok], key=lambda n: n.ping_ms)[:top]
    if not pool_nodes:
        return
    url = cfg.get("speed_url") or "https://speed.cloudflare.com/__down?bytes=1000000"
    timeout = float(cfg.get("speed_timeout", 12))
    batch = max(1, int(cfg.get("batch", 48)))
    base = int(cfg.get("port_base", 23100))
    span = max(batch, int(cfg.get("port_span", 4096)))
    port = free_block(base, span, len(pool_nodes))
    if port is None:
        return
    proc = Xray(exe)
    if not proc.start(batch_config(pool_nodes, port)):
        return
    try:
        if not proc.wait_ports([port + i for i in range(len(pool_nodes))], timeout=15):
            return

        def one(i: int, n: Node) -> None:
            cmd = ["curl", "-sS", "-o", DEVNULL, "-x", f"socks5h://127.0.0.1:{port + i}",
                   "--max-time", str(timeout), "-A", UA,
                   "-w", "%{speed_download};%{size_download}", url]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True,
                                     timeout=timeout + 6, env=_CLEAN_ENV,
                                     creationflags=_CREATE_NO_WINDOW)
            except Exception:                  # noqa: BLE001
                return
            parts = (res.stdout or "").strip().splitlines()
            if not parts:
                return
            chunk = parts[-1].split(";")
            try:
                speed_bps = float(chunk[0] or 0)
            except (ValueError, IndexError):
                return
            if speed_bps > 0:
                n.speed_mbps = round(speed_bps * 8 / 1e6, 2)

        with ThreadPoolExecutor(max_workers=len(pool_nodes)) as pool:
            for f in as_completed([pool.submit(one, i, n) for i, n in enumerate(pool_nodes)]):
                f.result()
    finally:
        proc.stop()
