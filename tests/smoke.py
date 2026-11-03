"""Быстрые проверки без запуска ядра: разбор ссылок, дедуп, QR, страница."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qrservice import nodes, site, subs  # noqa: E402

SAMPLES = [
    "vless://11111111-2222-3333-4444-555555555555@example.com:443?security=reality&sni=www.microsoft.com&fp=chrome&pbk=abcdefghijklmnopqrstuvwxyz0123456789ABCDEF&sid=ab12&type=tcp&flow=xtls-rprx-vision#%F0%9F%87%B3%F0%9F%87%B1%20NL-1",
    "vmess://eyJhZGQiOiJleGFtcGxlLm9yZyIsInBvcnQiOiI0NDMiLCJpZCI6ImFiY2RlZjEyMzQiLCJuZXQiOiJ3cyIsInRscyI6InRscyIsInBhdGgiOiIvd3MiLCJob3N0IjoiZXhhbXBsZS5vcmciLCJwcyI6IldTLXRlc3QifQ==",
    "trojan://password123@tro.example.com:8443?security=tls&sni=tro.example.com&type=grpc&path=svc#Trojan-test",
    "ss://YWVzLTI1Ni1nY206cGFzc3dvcmQ=@ss.example.net:8388#SS-test",
]


def main() -> int:
    got = [nodes.parse_uri(u, "unit") for u in SAMPLES]
    assert all(got), f"не разобраны: {[u[:30] for u, g in zip(SAMPLES, got) if not g]}"
    assert got[0].kind == "vless" and got[0].security == "reality" and got[0].pbk
    assert got[0].remarks.startswith("🇳🇱"), got[0].remarks
    assert got[1].kind == "vmess" and got[1].network == "ws" and got[1].security == "tls"
    assert got[2].kind == "trojan" and got[2].network == "grpc" and got[2].path == "svc"
    assert got[3].kind == "ss" and got[3].ss_method == "aes-256-gcm", got[3].ss_method
    assert all(n.supported for n in got)
    print("[ok] разбор vless/vmess/trojan/ss")

    dup = nodes.dedupe(got + [nodes.parse_uri(SAMPLES[0], "unit")])
    assert len(dup) == 4, len(dup)
    print("[ok] дедупликация")

    # base64-подписка
    import base64
    blob = base64.b64encode("\n".join(SAMPLES).encode()).decode()
    assert len(nodes.parse_text(blob, "b64")) == 4
    assert len(nodes.parse_text("\n".join(SAMPLES), "plain")) == 4
    print("[ok] подписка в base64 и простым текстом")

    svg = site.qr_svg(SAMPLES[0], scale=3)
    assert svg.startswith("<svg") and "</svg>" in svg
    print(f"[ok] QR-SVG собран, {len(svg)} символов")

    # Страница: 2 ноды, история, подпись подписки
    public = []
    for n in got[:2]:
        n.ok, n.ping_ms = True, 120.0
        d = n.to_public()
        d["security"] = n.security
        d["network"] = n.network
        public.append(d)
    state = {"updated": 1_700_000_000, "runs": 3,
             "nodes": {public[0]["id"]: {"ok": 3, "total": 3, "last_ok": 1_700_000_000,
                                         "link": public[0]["link"]}}}
    cfg = {"site": {"title": "Тест", "refresh_seconds": 60, "refresh_minutes": 20}}
    out = Path(__file__).resolve().parent / "_out"
    info = site.build_site(public, state, cfg, out, "slug123",
                           "https://user.github.io/repo/slug123/sub.txt", "Проверено локально")
    page = Path(info["page"]).read_text("utf-8")
    for needle in ("data-qr=", "qr/", "Подписка", "Как подключиться"):
        assert needle in page.replace("\\", "/"), needle
    assert (out / "slug123" / "qr" / f"{public[0]['id']}.svg").exists()
    assert (out / "slug123" / "sub.txt").read_text().strip()
    print(f"[ok] страница: {info['count']} карточек, kinds={info['kinds']}")
    print("[ok] все проверки пройдены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
