"""Сборка мобильной страницы: карточки серверов, QR-коды, файл подписки."""
from __future__ import annotations

import html
import io
import json
import time
from pathlib import Path

try:
    import segno
except ImportError:                            # pragma: no cover
    segno = None                               # type: ignore[assignment]

CSS = """
:root{--bg:#0a0e13;--card:#151c25;--card2:#1b2531;--txt:#e8eef6;--mut:#8b9bb0;
--acc:#4fa3ff;--ok:#3ddc84;--warn:#ffb020;--bad:#ff5f6d;--line:#243040}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;background:var(--bg);color:var(--txt)}
body{font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif;
padding-bottom:34px;-webkit-text-size-adjust:100%}
header{position:sticky;top:0;z-index:10;padding:13px 16px 10px;background:rgba(10,14,19,.94);
border-bottom:1px solid var(--line);backdrop-filter:blur(10px)}
h1{margin:0 0 3px;font-size:17px;font-weight:650;letter-spacing:.2px}
.stat{font-size:12.5px;color:var(--mut)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;
vertical-align:1px;background:var(--ok)}
.dot.warn{background:var(--warn)}
.dot.bad{background:var(--bad)}
main{max-width:720px;margin:0 auto;padding:12px 12px 0}
.hint{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:11px 13px;font-size:13.5px;color:var(--mut);margin-bottom:10px}
.hint b{color:var(--txt);font-weight:600}
.warnbox{border-color:#5a3a08;background:#241a08;color:#ffd79a;font-size:13.5px;
border-radius:14px;padding:11px 13px;margin-bottom:10px}
.chips{display:flex;gap:8px;overflow-x:auto;padding:2px 0 10px;scrollbar-width:none}
.chips::-webkit-scrollbar{display:none}
.chip{flex:0 0 auto;padding:9px 14px;border-radius:999px;background:var(--card);
border:1px solid var(--line);color:var(--mut);font-size:13.5px;font-weight:600;
cursor:pointer;font-family:inherit}
.chip.on{background:var(--acc);border-color:var(--acc);color:#04121f}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;
padding:13px 14px;margin-bottom:10px}
.top{display:flex;align-items:flex-start;gap:10px;justify-content:space-between}
.nm{font-weight:640;font-size:15px;line-height:1.28;word-break:break-word}
.ping{font-variant-numeric:tabular-nums;font-size:13px;font-weight:700;white-space:nowrap;
padding-top:1px}
.p-fast{color:var(--ok)}.p-mid{color:var(--warn)}.p-slow{color:var(--bad)}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin:9px 0 11px}
.tag{font-size:11px;padding:3px 8px;border-radius:6px;background:var(--card2);color:var(--mut)}
.tag.good{color:#8ff0b5;background:#12291c}
.tag.stale{color:#ffd79a;background:#2a1f08}
.acts{display:flex;gap:8px}
.btn{flex:1;min-height:44px;border-radius:12px;border:1px solid var(--line);
background:var(--card2);color:var(--txt);font:600 14.5px/1 inherit;display:flex;
align-items:center;justify-content:center;gap:6px;text-decoration:none;cursor:pointer;
padding:0 10px}
.btn.primary{background:var(--acc);border-color:var(--acc);color:#04121f}
.btn:active{transform:scale(.985)}
.btn[disabled]{opacity:.75}
.subblock{background:var(--card);border:1px solid var(--line);border-radius:16px;
padding:14px;margin:14px 0 8px}
.subblock h2{font-size:14.5px;margin:0 0 6px;font-weight:640}
.subblock p{margin:0 0 10px;font-size:13px;color:var(--mut)}
.subrow{display:flex;gap:10px;align-items:center}
.subrow img{width:96px;height:96px;background:#fff;border-radius:10px;padding:4px;flex:0 0 auto}
.url{font:12px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--acc);
word-break:break-all;margin-bottom:8px}
footer{max-width:720px;margin:16px auto 0;padding:0 14px;font-size:12px;color:var(--mut);
text-align:center;line-height:1.6}
.ovl{position:fixed;inset:0;z-index:50;display:none;align-items:center;justify-content:center;
padding:18px;background:rgba(4,7,10,.92);backdrop-filter:blur(4px)}
.ovl.show{display:flex}
.ovl-box{width:100%;max-width:370px;background:#0f151d;border:1px solid var(--line);
border-radius:20px;padding:14px 14px 16px}
.ovl-head{display:flex;align-items:flex-start;gap:10px;justify-content:space-between;
margin-bottom:10px}
.ovl-title{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--mut);
margin-bottom:3px}
.ovl-head .nm{font-size:14px}
#ovl-x{flex:0 0 auto;width:32px;height:32px;border-radius:50%;background:var(--card2);
border:0;color:var(--txt);font-size:18px;line-height:1;cursor:pointer}
.qrwrap{background:#fff;border-radius:14px;padding:10px;margin-bottom:9px}
#ovl-qr{display:block;width:100%;height:auto}
.ovl-tip{font-size:12px;color:var(--mut);text-align:center;margin-bottom:9px;line-height:1.4}
.ovl-lnk{font:11.5px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;color:#a8bacd;
max-height:40px;overflow:hidden;word-break:break-all;margin-bottom:10px;cursor:pointer;
border:1px dashed var(--line);border-radius:10px;padding:7px 9px}
.ovl-lnk.open{max-height:132px;overflow:auto}
.urlhint{font-size:11.5px;color:var(--acc);margin:-4px 0 10px 2px;cursor:pointer}
.none{display:none;color:var(--mut);font-size:14px;text-align:center;padding:26px 0}
@media (prefers-color-scheme:light){
 :root{--bg:#f5f7fa;--card:#fff;--card2:#eef2f8;--txt:#0e1520;--mut:#5c6b7f;--line:#dde4ee;--acc:#1a6fd4}
 header{background:rgba(245,247,250,.95)}
 .tag.good{color:#0a6b34;background:#e2f7ea}
 .tag.stale{color:#7a4a00;background:#fff2d8}
 .warnbox{border-color:#f0c67a;background:#fff8e8;color:#6b4400}
 .ovl-box{background:#fff}
 .ovl-lnk{color:#5c6b7f}
}
"""

JS = r"""
(function(){
  var REFRESH = __REFRESH__;
  var ovl = document.getElementById('ovl');
  var qrImg = document.getElementById('ovl-qr');
  var linkEl = document.getElementById('ovl-link');
  var nameEl = document.getElementById('ovl-name');
  var dl = document.getElementById('ovl-dl');
  var cur = '';
  function copyText(t){
    if (navigator.clipboard && window.isSecureContext) { return navigator.clipboard.writeText(t); }
    return new Promise(function(res, rej){
      var ta = document.createElement('textarea');
      ta.value = t; ta.setAttribute('readonly','');
      ta.style.position = 'fixed'; ta.style.top = '-1000px';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); res(); } catch(e){ rej(e); }
      document.body.removeChild(ta);
    });
  }
  function flash(btn, txt){
    if (!btn) { return; }
    var old = btn.textContent;
    btn.textContent = txt; btn.disabled = true;
    setTimeout(function(){ btn.textContent = old; btn.disabled = false; }, 1300);
  }
  function openQr(id, name, link){
    cur = link; nameEl.textContent = name;
    qrImg.src = 'qr/' + id + '.svg';
    dl.href = 'qr/' + id + '.svg';
    linkEl.textContent = link;
    linkEl.classList.remove('open');
    document.getElementById('ovl-more').textContent = 'Показать ссылку полностью';
    ovl.classList.add('show');
  }
  function closeQr(){ ovl.classList.remove('show'); }
  document.addEventListener('click', function(e){
    var t = e.target;
    if (t.id === 'ovl-link' || t.id === 'ovl-more') {
      var opened = linkEl.classList.toggle('open');
      document.getElementById('ovl-more').textContent =
        opened ? 'Скрыть' : 'Показать ссылку полностью';
      return;
    }
    var b = t.closest ? t.closest('[data-qr]') : null;
    if (b) { openQr(b.getAttribute('data-qr'), b.getAttribute('data-name'),
                    b.getAttribute('data-link')); return; }
    var c = t.closest ? t.closest('[data-copy]') : null;
    if (c) {
      var val = c.getAttribute('data-copy');
      copyText(val).then(function(){ flash(c, 'Скопировано'); })
                   .catch(function(){ flash(c, 'Ошибка'); });
      return;
    }
    if (t.id === 'ovl' || t.id === 'ovl-x') { closeQr(); return; }
    var f = t.closest ? t.closest('[data-filter]') : null;
    if (f) { setFilter(f.getAttribute('data-filter')); }
  });
  document.getElementById('ovl-copy').addEventListener('click', function(){
    var b = this;
    copyText(cur).then(function(){ flash(b, 'Скопировано'); }).catch(function(){ flash(b,'Ошибка'); });
  });
  document.addEventListener('keydown', function(e){ if (e.key === 'Escape') { closeQr(); } });
  function setFilter(f){
    var chips = document.querySelectorAll('[data-filter]');
    for (var i = 0; i < chips.length; i++) {
      chips[i].classList.toggle('on', chips[i].getAttribute('data-filter') === f);
    }
    var cards = document.querySelectorAll('.card');
    var shown = 0;
    for (var j = 0; j < cards.length; j++) {
      var card = cards[j];
      var up = parseFloat(card.getAttribute('data-up') || '0');
      var ok = (f === 'all') || (f === 'stable' ? up >= 0.8 : card.getAttribute('data-kind') === f);
      card.style.display = ok ? '' : 'none';
      if (ok) { shown++; }
    }
    document.getElementById('none').style.display = shown ? 'none' : 'block';
  }
  function tick(){
    var els = document.querySelectorAll('[data-ts]');
    for (var i = 0; i < els.length; i++) {
      var ts = parseInt(els[i].getAttribute('data-ts'), 10) * 1000;
      if (!ts) { continue; }
      var m = Math.round((Date.now() - ts) / 60000);
      els[i].textContent = m < 1 ? 'только что' : (m < 60 ? m + ' мин назад'
                                   : (m < 1440 ? Math.round(m / 60) + ' ч назад'
                                   : Math.round(m / 1440) + ' дн назад'));
    }
  }
  tick(); setInterval(tick, 30000);
  if (REFRESH > 0) {
    setTimeout(function(){ if (!ovl.classList.contains('show')) { location.reload(); } },
               REFRESH * 1000);
  }
})();
"""

PAGE = """<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow,noarchive">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#0a0e13">
<title>__TITLE__</title>
<style>__CSS__</style>
</head><body>
<header>
  <h1>__TITLE__</h1>
  <div class="stat"><span class="dot __STATE__"></span>__ALIVE__ · обновлено <span data-ts="__TS__">__AGO__</span></div>
  <div class="stat" style="margin-top:2px">__ORIGIN__</div>
</header>
<main>
__WARN__
<div class="hint">
  <b>Как подключиться:</b> установите клиент (v2rayNG, Hiddify, Streisand, Shadowrocket) →
  нажмите <b>QR-код</b> у сервера и отсканируйте его камерой телефона, либо нажмите
  <b>Копировать</b> и вставьте ссылку в клиенте через «Импорт из буфера обмена».
</div>
<div class="chips">
  <button class="chip on" data-filter="all">Все (__ALIVE_N__)</button>
  <button class="chip" data-filter="stable">Стабильные</button>
  __CHIPS__
</div>
<div id="list">__CARDS__</div>
<div class="none" id="none">В этой категории пока нет серверов</div>
__SUB__
</main>
<footer>
  Проверка: реальный запрос через сервер каждые __REFRESH_MIN__ мин. Сервер попадает в список,
  только если через него прошёл трафик.<br>
  Страница обновляется автоматически, ссылки живут до следующей проверки.
</footer>
<div class="ovl" id="ovl">
  <div class="ovl-box">
    <div class="ovl-head">
      <div>
        <div class="ovl-title">QR-код подключения</div>
        <div class="nm" id="ovl-name"></div>
      </div>
      <button id="ovl-x" aria-label="Закрыть">×</button>
    </div>
    <div class="qrwrap"><img id="ovl-qr" alt="QR-код подключения"></div>
    <div class="ovl-tip">Наведите камеру телефона или откройте в клиенте
      «＋» → «Сканировать QR-код»</div>
    <div class="ovl-lnk" id="ovl-link" title="Нажмите, чтобы развернуть ссылку"></div>
    <div class="urlhint" id="ovl-more">Показать ссылку полностью</div>
    <div class="acts">
      <button class="btn primary" id="ovl-copy">Скопировать ссылку</button>
      <a class="btn" id="ovl-dl" download="qr.svg">Скачать QR</a>
    </div>
  </div>
</div>
<script>__JS__</script>
</body></html>
"""

CARD = """<article class="card" data-kind="__KIND__" data-up="__UP__" data-id="__ID__">
  <div class="top">
    <div class="nm">__NAME__</div>
    <div class="ping __PCLS__">__PING__</div>
  </div>
  <div class="tags">__TAGS__</div>
  <div class="acts">
    <button class="btn primary" data-qr="__ID__" data-name="__NAME2__" data-link="__LINK__">QR-код</button>
    <button class="btn" data-copy="__LINK__">Копировать</button>
  </div>
</article>"""


def qr_svg(text: str, scale: int = 4, border: int = 2) -> str:
    """QR-код в виде SVG-разметки (без внешних зависимостей в рантайме)."""
    if segno is None:
        raise RuntimeError("не установлен пакет segno: pip install segno")
    qr = segno.make(text, error="m", boost_error=False)
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=scale, border=border, dark="#000", light="#fff")
    svg = buf.getvalue().decode("utf-8")
    start = svg.find("<svg")
    return svg[start:] if start >= 0 else svg


def write_qr(path: Path, text: str, scale: int = 4) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(qr_svg(text, scale=scale), encoding="utf-8")


def _esc(value: str) -> str:
    return html.escape(str(value), quote=True)


def _ping_class(ms: float) -> str:
    if ms <= 0:
        return "p-slow"
    return "p-fast" if ms < 200 else ("p-mid" if ms < 450 else "p-slow")


def _uptime(state_node: dict | None) -> float:
    if not state_node:
        return 0.0
    total = int(state_node.get("total") or 0)
    if total <= 0:
        return 0.0
    return round(int(state_node.get("ok") or 0) / total, 2)


def sort_key(node: dict, state_node: dict | None) -> float:
    """Чем меньше — тем выше в списке: быстрый узел, который ещё и стабилен."""
    ping = float(node.get("ping") or 900)
    up = _uptime(state_node)
    return ping * (1 + 2.0 * (1.0 - up))


def build_site(nodes: list[dict], state: dict, cfg: dict, out_root: Path,
               slug: str, sub_url: str, origin: str, stale: bool = False) -> dict:
    """Пишет страницу, QR-коды и файл подписки. Возвращает сводку."""
    site_cfg = cfg.get("site", {}) or {}
    out = out_root / slug
    out.mkdir(parents=True, exist_ok=True)
    (out / "qr").mkdir(exist_ok=True)
    (out_root / ".nojekyll").write_text("", encoding="utf-8")

    nodes = [n for n in nodes if n.get("link")]
    state_nodes = state.get("nodes", {}) or {}
    for n in nodes:
        st = state_nodes.get(n["id"])
        n["uptime"] = _uptime(st)
        n["state"] = st

    nodes.sort(key=lambda n: sort_key(n, n.get("state")))

    cards: list[str] = []
    kinds: dict[str, int] = {}
    for n in nodes:
        write_qr(out / "qr" / f"{n['id']}.svg", n["link"], scale=4)
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
        tags = [f'<span class="tag">{n["kind"].upper()}</span>']
        if n.get("security"):
            tags.append(f'<span class="tag">{n["security"].upper()}</span>')
        if n.get("network") and n["network"] != "raw":
            tags.append(f'<span class="tag">{n["network"]}</span>')
        if n.get("age"):
            tags.append(f'<span class="tag age">проверен {n["age"]} мин назад</span>')
        if stale:
            tags.append('<span class="tag stale">не проверен сейчас</span>')
        elif n["uptime"] >= 0.8:
            tags.append(f'<span class="tag good">{int(round(n["uptime"] * 100))}% аптайм</span>')
        if n.get("source"):
            tags.append(f'<span class="tag">{_esc(n["source"])[:28]}</span>')
        ping = f'{int(round(n["ping"]))} мс' if n.get("ping") else "—"
        cards.append(CARD
                     .replace("__KIND__", _esc(n["kind"]))
                     .replace("__UP__", f'{n["uptime"]:.2f}')
                     .replace("__ID__", _esc(n["id"]))
                     .replace("__NAME__", _esc(n["name"]))
                     .replace("__NAME2__", _esc(n["name"]))
                     .replace("__PCLS__", _ping_class(float(n.get("ping") or 0)))
                     .replace("__PING__", _esc(ping))
                     .replace("__TAGS__", "".join(tags))
                     .replace("__LINK__", _esc(n["link"])))

    chips = "".join(
        f'<button class="chip" data-filter="{k}">{k.upper()} ({v})</button>'
        for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])
    )

    sub_block = ""
    sub_target = sub_url or "sub.txt"
    if sub_target:
        qr_part = ""
        if sub_url:
            write_qr(out / "qr" / "sub.svg", sub_url, scale=4)
            qr_part = '<img src="qr/sub.svg" alt="QR подписки">'
        note = ("Вставьте эту ссылку в клиент (v2rayNG: «Подписки» → «＋» → вставить URL) "
                "или отсканируйте QR — клиент будет сам подтягивать свежий список серверов."
                if sub_url else
                "Файл подписки лежит рядом со страницей. Чтобы получить ссылку для клиента, "
                "задайте PAGES_URL (адрес, по которому открывается эта страница).")
        sub_block = (
            '<div class="subblock"><h2>Подписка — серверы обновляются сами</h2>'
            f'<p>{note}</p>'
            f'<div class="url">{_esc(sub_target)}</div>'
            '<div class="subrow">' + qr_part +
            '<div style="flex:1">'
            f'<button class="btn primary" data-copy="{_esc(sub_target)}">Копировать ссылку</button>'
            '</div></div></div>'
        )

    ts = int(state.get("updated") or time.time())
    alive = len(nodes)
    if stale:
        warn = ('<div class="warnbox">Сейчас проверка не нашла рабочих серверов — ниже '
                'последние, что работали недавно. Они могут быть уже недоступны.</div>')
        state_dot = "warn"
        alive_text = f"0 рабочих сейчас · {alive} по последней удачной проверке"
    else:
        warn = ""
        state_dot = "ok" if alive else "bad"
        alive_text = f"{alive} рабочих серверов"

    page = (PAGE
            .replace("__TITLE__", _esc(site_cfg.get("title") or "Рабочие серверы"))
            .replace("__CSS__", CSS)
            .replace("__JS__", JS.replace("__REFRESH__", str(int(site_cfg.get("refresh_seconds", 120)))))
            .replace("__STATE__", state_dot)
            .replace("__ALIVE__", alive_text)
            .replace("__ALIVE_N__", str(alive))
            .replace("__TS__", str(ts))
            .replace("__AGO__", "недавно")
            .replace("__ORIGIN__", _esc(origin))
            .replace("__WARN__", warn)
            .replace("__CHIPS__", chips)
            .replace("__CARDS__", "".join(cards) or
                     '<div class="none" style="display:block">Пока нет ни одного проверенного сервера</div>')
            .replace("__SUB__", sub_block)
            .replace("__REFRESH_MIN__", str(int(site_cfg.get("refresh_minutes", 15)))))
    (out / "index.html").write_text(page, encoding="utf-8")

    links = "\n".join(n["link"] for n in nodes)
    import base64
    (out / "sub.txt").write_text(
        base64.b64encode(links.encode("utf-8")).decode("ascii"), encoding="utf-8")
    (out / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    # нейтральная заглушка в корне — чтобы каталог не выглядел каталогом ссылок
    if not (out_root / "index.html").exists():
        (out_root / "index.html").write_text(
            '<!doctype html><meta charset="utf-8"><title>ok</title>'
            '<body style="background:#0a0e13;color:#8b9bb0;font:15px system-ui;'
            'display:flex;align-items:center;justify-content:center;height:100vh">ok</body>',
            encoding="utf-8")

    return {"page": str(out / "index.html"), "count": len(nodes),
            "sub": str(out / "sub.txt"), "kinds": kinds}
