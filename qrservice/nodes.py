"""Разбор share-ссылок (vless://, vmess://, trojan://, ss://) в структуру Node.

Логика взята из проверенного `v2rayn_auto/parsers.py` проекта hermscr и
упрощена: остаются только поля, которые влияют на подключение и на QR-код.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import urllib.parse
from dataclasses import dataclass

SCHEMES = ("vless", "vmess", "trojan", "ss")
#: Транспорты, которые понимает ядро Xray в актуальной версии (h2 из него убран).
NETWORKS = {"raw", "ws", "grpc", "xhttp", "httpupgrade", "kcp"}
#: В подписках tcp называется по-старому, а в конфиге ядра он — raw.
NET_ALIAS = {"tcp": "raw", "": "raw", "http": "raw", "h2": "h2"}


def _b64(data: str) -> str:
    """Мягкий base64-декод: url-safe, без padding, мусор по краям игнорируется."""
    s = (data or "").strip().replace("-", "+").replace("_", "/")
    pad = "=" * (-len(s) % 4)
    for cand in (s + pad, s):
        try:
            return base64.b64decode(cand).decode("utf-8", "ignore")
        except (binascii.Error, ValueError):
            continue
    return ""


def _q(query: str) -> dict[str, str]:
    return {k.lower(): v for k, v in urllib.parse.parse_qsl(query or "", keep_blank_values=True)}


@dataclass
class Node:
    kind: str
    remarks: str
    address: str
    port: int
    secret: str                 # uuid (vless/vmess) или пароль (trojan/ss)
    network: str = "raw"
    security: str = ""          # "" | tls | reality
    sni: str = ""
    alpn: str = ""
    fp: str = ""
    pbk: str = ""
    sid: str = ""
    spx: str = ""
    flow: str = ""
    host: str = ""
    path: str = ""
    mode: str = ""
    ss_method: str = ""
    alter_id: int = 0
    allow_insecure: bool = False
    xhttp_extra: str = ""
    source: str = ""
    link: str = ""
    # --- результаты последней проверки (в конфиг не попадают) --------------
    ping_ms: float = 0.0
    ok: bool = False
    error: str = ""

    # --- свойства ---------------------------------------------------------
    @property
    def ident(self) -> str:
        """Ключ дедупликации: всё, что влияет на соединение."""
        raw = "|".join([
            self.kind, self.address.lower(), str(self.port), self.secret,
            self.network, self.security, self.pbk, self.sid, self.sni,
            self.host, self.path, self.flow, self.mode, self.ss_method,
        ])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def label(self) -> str:
        return (self.remarks or "").strip() or f"{self.address}:{self.port}"

    @property
    def supported(self) -> bool:
        if self.kind not in SCHEMES:
            return False
        if not self.address or not 0 < int(self.port) < 65536 or not self.secret:
            return False
        if self.network not in NETWORKS:
            return False
        if self.kind == "ss" and (not self.ss_method or self.ss_method == "none"):
            return False
        if self.security == "reality" and not self.pbk:
            return False
        return True

    def to_public(self) -> dict:
        """То, что нужно странице и клиенту (без служебных полей)."""
        return {
            "id": self.ident,
            "kind": self.kind,
            "name": self.label,
            "address": self.address,
            "port": self.port,
            "network": self.network,
            "security": self.security,
            "ping": round(self.ping_ms, 1),
            "link": self.link,
            "source": self.source,
        }


def _apply_stream(node: Node, q: dict[str, str]) -> None:
    sec = (q.get("security") or "").lower()
    if sec in ("tls", "reality", "xtls"):
        node.security = "tls" if sec == "xtls" else sec
    node.sni = q.get("sni") or q.get("peer") or q.get("host") or ""
    node.alpn = q.get("alpn") or ""
    node.fp = q.get("fp") or ""
    node.pbk = q.get("pbk") or ""
    node.sid = q.get("sid") or ""
    node.spx = q.get("spx") or ""
    node.allow_insecure = str(q.get("allowinsecure", "")).lower() in ("1", "true")
    node.network = (q.get("type") or q.get("net") or "raw").lower() or "raw"
    node.network = NET_ALIAS.get(node.network, node.network)
    node.host = q.get("host") or ""
    node.path = q.get("path") or ""
    node.mode = q.get("mode") or ""
    if node.network == "xhttp":
        node.xhttp_extra = q.get("extra") or ""


def _parse_vless(uri: str) -> Node | None:
    p = urllib.parse.urlsplit(uri)
    if not p.hostname:
        return None
    q = _q(p.query)
    n = Node(kind="vless", remarks=urllib.parse.unquote(p.fragment or ""),
             address=p.hostname, port=int(p.port or 443),
             secret=urllib.parse.unquote(p.username or ""))
    n.flow = q.get("flow") or ""
    _apply_stream(n, q)
    return n


def _parse_trojan(uri: str) -> Node | None:
    p = urllib.parse.urlsplit(uri)
    if not p.hostname:
        return None
    q = _q(p.query)
    n = Node(kind="trojan", remarks=urllib.parse.unquote(p.fragment or ""),
             address=p.hostname, port=int(p.port or 443),
             secret=urllib.parse.unquote(p.username or ""))
    _apply_stream(n, q)
    if not n.security:
        n.security = "tls"
    return n


def _parse_vmess(uri: str) -> Node | None:
    body = _b64(uri.split("://", 1)[1].split("#", 1)[0])
    if not body:
        return None
    d = json.loads(body)
    net = str(d.get("net") or "tcp").lower()
    n = Node(kind="vmess",
             remarks=str(d.get("ps") or ""),
             address=str(d.get("add") or ""),
             port=int(d.get("port") or 443),
             secret=str(d.get("id") or ""))
    n.network = {"tcp": "raw", "h2": "h2"}.get(net, net) or "raw"
    sec = str(d.get("tls") or "").lower()
    n.security = sec if sec in ("tls", "reality") else ""
    n.sni = str(d.get("sni") or d.get("host") or "")
    n.alpn = str(d.get("alpn") or "")
    n.fp = str(d.get("fp") or "")
    n.pbk = str(d.get("pbk") or "")
    n.sid = str(d.get("sid") or "")
    n.alter_id = int(d.get("aid") or 0)
    n.host = str(d.get("host") or "")
    n.path = str(d.get("path") or "")
    n.mode = str(d.get("type") or "") if n.network in ("grpc", "xhttp") else ""
    return n


def _parse_ss(uri: str) -> Node | None:
    p = urllib.parse.urlsplit(uri)
    method = password = ""
    host = p.hostname or ""
    port = int(p.port or 0)
    if p.username is not None and host:
        decoded = _b64(p.username) or urllib.parse.unquote(p.username)
        if ":" not in decoded:
            return None
        method, password = decoded.split(":", 1)
    else:
        decoded = _b64(uri.split("://", 1)[1].split("#", 1)[0])
        if "@" not in decoded:
            return None
        userinfo, hostport = decoded.rsplit("@", 1)
        if ":" not in userinfo or ":" not in hostport:
            return None
        method, password = userinfo.split(":", 1)
        host, port_s = hostport.rsplit(":", 1)
        port = int(port_s)
    q = _q(p.query)
    n = Node(kind="ss", remarks=urllib.parse.unquote(p.fragment or ""),
             address=host, port=port, secret=password,
             ss_method=method.strip().lower())
    n.network = "raw"
    n.security = "tls" if (q.get("security") or "").lower() == "tls" else ""
    n.sni = q.get("sni") or ""
    return n


_PARSERS = {"vless": _parse_vless, "vmess": _parse_vmess,
            "trojan": _parse_trojan, "ss": _parse_ss}


def parse_uri(uri: str, source: str = "") -> Node | None:
    uri = (uri or "").strip()
    if "://" not in uri:
        return None
    scheme = uri.split("://", 1)[0].lower()
    if scheme not in _PARSERS:
        return None
    try:
        node = _PARSERS[scheme](uri)
    except Exception:                      # noqa: BLE001 — битые строки это норма
        return None
    if node is None:
        return None
    node.source = source
    node.link = uri
    if not node.remarks:
        node.remarks = f"{node.address}:{node.port}"
    return node if node.supported else None


def parse_text(text: str, source: str = "") -> list[Node]:
    """Разбирает подписку: список ссылок (по строкам) или base64-блок."""
    text = (text or "").strip()
    if not text:
        return []
    out: list[Node] = []
    seen: set[str] = set()

    def feed(block: str) -> None:
        for line in block.replace("\r", "\n").split("\n"):
            line = line.strip()
            if not line or line.startswith(("#", "//")):
                continue
            for token in line.split():
                if "://" not in token or token in seen:
                    continue
                node = parse_uri(token, source)
                if node:
                    seen.add(token)
                    out.append(node)

    feed(text)
    if not out:
        feed(_b64(text))
    return out


def dedupe(nodes: list[Node]) -> list[Node]:
    """Оставляет по одной записи на конфигурацию; имя выбирается покороче."""
    best: dict[str, Node] = {}
    for n in nodes:
        key = n.ident
        cur = best.get(key)
        if cur is None or len(n.remarks) < len(cur.remarks):
            best[key] = n
    return list(best.values())
