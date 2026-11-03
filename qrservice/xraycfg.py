"""Сборка конфигов Xray: outbound ноды и батч-конфиг на N нод.

Идея (и все грабли) взяты из `v2rayn_auto/xrayconf.py` проекта hermscr:
один процесс ядра обслуживает N socks-inbound'ов, каждый маршрутизируется
в свой outbound — так на батч из 48 нод нужен один процесс вместо 48.
"""
from __future__ import annotations

import json
import socket
from typing import Any

from .nodes import Node

DEFAULT_FP = "chrome"
EMAIL = "t@t.tt"
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _as_bool(v: Any) -> Any:
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        t = v.strip().lower()
        if t in _TRUE:
            return True
        if t in _FALSE:
            return False
    return v


def _as_int(v: Any) -> Any:
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        try:
            return int(v.strip())
        except ValueError:
            return v
    return v


def _xhttp_extra(raw: str) -> dict:
    """`extra` xhttp: Xray принимает строгие bool/int поля только нужного типа.

    Один узел со строкой "false" вместо false валит запуск всего ядра, и тогда
    непроверенным остаётся целый батч. Поэтому типы приводим, а неразбираемое
    выбрасываем — значения по умолчанию у Xray безопаснее падения.
    """
    try:
        data = json.loads(raw) if raw else {}
    except Exception:                      # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    clean = dict(data)
    for k in ("noGRPCHeader", "noSSEHeader", "xPaddingObfsMode"):
        if k in clean:
            v = _as_bool(clean[k])
            clean[k] = v if isinstance(v, bool) else clean.pop(k)
    for k in ("scMaxBufferedPosts", "serverMaxHeaderBytes"):
        if k in clean:
            v = _as_int(clean[k])
            clean[k] = v if isinstance(v, int) and not isinstance(v, bool) else clean.pop(k)
    xmux = clean.get("xmux")
    if isinstance(xmux, dict):
        xmux = dict(xmux)
        if "hKeepAlivePeriod" in xmux:
            v = _as_int(xmux["hKeepAlivePeriod"])
            xmux["hKeepAlivePeriod"] = v if isinstance(v, int) else xmux.pop("hKeepAlivePeriod")
        clean["xmux"] = xmux
    for k in ("downloadSettings", "extra"):
        if k in clean and clean[k] is None:
            clean.pop(k)
    return clean


def build_outbound(n: Node, tag: str = "proxy") -> dict:
    out: dict[str, Any] = {
        "tag": tag,
        "protocol": n.kind,
        "settings": {},
        "streamSettings": {},
        "mux": {"enabled": False, "concurrency": -1},
    }
    st = out["settings"]

    if n.kind == "vless":
        user: dict[str, Any] = {"id": n.secret, "email": EMAIL, "encryption": "none"}
        if n.flow:
            user["flow"] = n.flow
        st["vnext"] = [{"address": n.address, "port": int(n.port), "users": [user]}]
    elif n.kind == "vmess":
        st["vnext"] = [{"address": n.address, "port": int(n.port), "users": [{
            "id": n.secret, "alterId": int(n.alter_id or 0), "email": EMAIL,
            "security": "auto",
        }]}]
    elif n.kind == "trojan":
        st["servers"] = [{"address": n.address, "port": int(n.port),
                          "password": n.secret, "ota": False, "level": 1}]
    elif n.kind == "ss":
        st["servers"] = [{"address": n.address, "port": int(n.port),
                          "password": n.secret, "method": n.ss_method,
                          "ota": False, "level": 1}]
    else:
        raise ValueError(f"неподдерживаемый тип: {n.kind}")

    _stream(n, out)
    return out


def _stream(n: Node, out: dict) -> None:
    ss = out["streamSettings"]
    network = n.network if n.network in ("raw", "ws", "grpc", "xhttp", "httpupgrade", "kcp") else "raw"
    ss["network"] = network

    if network == "ws":
        ws = {}
        if n.host:
            ws["host"] = n.host
        if n.path:
            ws["path"] = n.path
        ss["wsSettings"] = ws
    elif network == "httpupgrade":
        hu = {}
        if n.host:
            hu["host"] = n.host
        if n.path:
            hu["path"] = n.path
        ss["httpupgradeSettings"] = hu
    elif network == "xhttp":
        xh = {}
        if n.path:
            xh["path"] = n.path
        if n.host:
            xh["host"] = n.host
        if n.mode in ("auto", "packet-up", "stream-up", "stream-one"):
            xh["mode"] = n.mode
        extra = _xhttp_extra(n.xhttp_extra)
        if extra:
            xh["extra"] = extra
        ss["xhttpSettings"] = xh
    elif network == "grpc":
        g = {"serviceName": n.path or ""}
        if n.host:
            g["authority"] = n.host
        if n.mode == "multi":
            g["multiMode"] = True
        ss["grpcSettings"] = g
    elif network == "kcp":
        kcp = {}
        if n.host:
            kcp["seed"] = n.host
        ss["kcpSettings"] = kcp

    if n.security == "tls":
        ss["security"] = "tls"
        tls: dict[str, Any] = {"fingerprint": n.fp or DEFAULT_FP}
        # allowInsecure из ядра убран (Xray 26+): с ним ядро не стартует вовсе.
        # Ближайший поддерживаемый аналог — проверка сертификата по имени из SNI.
        if n.allow_insecure and n.sni:
            tls["verifyPeerCertByName"] = n.sni
        if n.alpn:
            alpn = [a.strip() for a in n.alpn.split(",") if a.strip()]
            if alpn:
                tls["alpn"] = alpn
        if n.sni:
            tls["serverName"] = n.sni
        elif n.host:
            tls["serverName"] = n.host.split(",")[0].strip()
        ss["tlsSettings"] = tls
    elif n.security == "reality":
        ss["security"] = "reality"
        ss["realitySettings"] = {
            "show": False,
            "fingerprint": n.fp or DEFAULT_FP,
            "serverName": n.sni,
            "publicKey": n.pbk,
            "shortId": n.sid or "",
            "spiderX": n.spx or "",
        }
    else:
        ss["security"] = "none"


def batch_config(nodes: list[Node], base_port: int, host: str = "127.0.0.1") -> dict:
    """N socks-inbound'ов -> N outbound'ов. Порт base_port+i принадлежит nodes[i]."""
    inbounds, outbounds, rules = [], [], []
    for i, node in enumerate(nodes):
        tag = f"n{i + 1}"
        inbounds.append({
            "tag": f"in{i + 1}", "port": int(base_port) + i, "listen": host,
            "protocol": "socks", "settings": {"auth": "noauth", "udp": False},
        })
        outbounds.append(build_outbound(node, tag))
        rules.append({"type": "field", "inboundTag": [f"in{i + 1}"], "outboundTag": tag})
    rules.append({"type": "field", "port": "0-65535", "outboundTag": "block"})
    return {
        "log": {"loglevel": "warning"},
        "inbounds": inbounds,
        "outbounds": outbounds + [{"tag": "direct", "protocol": "freedom"},
                                 {"tag": "block", "protocol": "blackhole"}],
        "routing": {"domainStrategy": "AsIs", "rules": rules},
    }


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def free_block(base: int, span: int, count: int, host: str = "127.0.0.1") -> int | None:
    """Первый непрерывный блок из `count` свободных портов в [base, base+span)."""
    if count <= 0 or count > span:
        return None
    for start in range(base, base + span - count + 1):
        if all(_port_free(p, host) for p in range(start, start + count)):
            return start
    return None
