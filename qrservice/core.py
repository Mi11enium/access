"""Запуск ядра Xray и ожидание готовности портов."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
IS_WIN = os.name == "nt"


def find_xray(explicit: str | None = None) -> str | None:
    """Ищет бинарь ядра: аргумент → XRAY_BIN → bin/ → PATH → папка v2rayN."""
    cands: list[str] = []
    if explicit:
        cands.append(explicit)
    env = os.environ.get("XRAY_BIN")
    if env:
        cands.append(env)
    here = Path(__file__).resolve().parent.parent
    exe = "xray.exe" if IS_WIN else "xray"
    cands += [str(here / "bin" / exe), str(Path.cwd() / "bin" / exe), exe]
    found = shutil.which(exe)
    if found:
        cands.append(found)
    if IS_WIN:
        cands += [
            r"D:/Software/v2rayN/v2rayN-windows-64/bin/xray/xray.exe",
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "v2rayN/bin/xray/xray.exe"),
        ]
    for c in cands:
        if c and Path(c).exists():
            return str(c)
    return None


class Xray:
    """Один процесс ядра на батч нод."""

    def __init__(self, exe: str, log_path: Path | None = None):
        self.exe = exe
        self.log_path = log_path or Path(tempfile.gettempdir()) / "qrservice-xray.log"
        self.proc: subprocess.Popen | None = None
        self._cfg_path: str | None = None

    def start(self, config: dict) -> bool:
        fd, path = tempfile.mkstemp(prefix="xray-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(config, fh, ensure_ascii=False)
        self._cfg_path = path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(self.log_path, "ab")
        try:
            self.proc = subprocess.Popen(
                [self.exe, "run", "-c", path],
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW if IS_WIN else 0,
            )
        except OSError as exc:
            print(f"[xray] не запустился: {exc}", file=sys.stderr)
            log.close()
            return False
        finally:
            log.close()
        return True

    def wait_ports(self, ports: list[int], timeout: float = 12.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                return False                      # ядро упало — ждать нечего
            if all(_port_open(p) for p in ports):
                return True
            time.sleep(0.15)
        return False

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:                      # noqa: BLE001
                try:
                    self.proc.kill()
                except Exception:                  # noqa: BLE001
                    pass
        self.proc = None
        if self._cfg_path:
            try:
                os.unlink(self._cfg_path)
            except OSError:
                pass
            self._cfg_path = None

    def tail(self, lines: int = 6) -> str:
        try:
            text = self.log_path.read_text("utf-8", errors="ignore").strip().splitlines()
        except OSError:
            return ""
        return " | ".join(text[-lines:])[:400]


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def xray_version(exe: str) -> str:
    try:
        out = subprocess.run([exe, "version"], capture_output=True, text=True, timeout=15,
                             creationflags=CREATE_NO_WINDOW if IS_WIN else 0)
        return (out.stdout or out.stderr or "").strip().splitlines()[0][:60]
    except Exception as exc:                   # noqa: BLE001
        return f"неизвестно ({exc})"
