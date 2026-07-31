#!/usr/bin/env python3
"""
chat.py — поиск по экспорту Telegram-чата с определением топика и готовыми
ссылками на сообщения.

Зачем: материал вики берётся из экспорта истории чата (каталог
`Чат продления ВНЖ/`, в .gitignore). Ссылка на сообщение имеет вид
`t.me/aimairn/<topic_id>/<msg_id>`, но поля «топик» в экспорте нет — его
приходится вычислять. Этот модуль делает и то, и другое.

Использование как CLI:

    tools/chat.py 'deferimento t[áa]cito'              # поиск по всему чату
    tools/chat.py 'tácito' --topic 43113 --min-len 800 # ветка + длинные сообщения
    tools/chat.py '#кейспортал' --limit 50 --chars 400
    tools/chat.py --id 110356                          # прочитать сообщение целиком

Использование как библиотеки:

    from chat import load, root_of, link
    msgs = load()
    print(link(110356))

Требует `jq` (извлечение из 130-МБ result.json) — первый запуск строит кэш
в `.cache/`, дальнейшие читают его.
"""
import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPORT_DIR = ROOT / "Чат продления ВНЖ"
CACHE_DIR = ROOT / ".cache"

# Карта форумных топиков группы: id → название (актуальное, с учётом
# переименований). Восстановлена из служебных сообщений полного экспорта.
TOPICS = {
    1: "General",
    43113: "До 30.06.2025",
    43114: "После 30.06.2025",
    54553: "Прочие ошибки продления",
    54908: "Команда NISS",
    63969: "H54 DN номады",
    64074: "Студенты",
    68636: "Ошибка печати/отмена после аппрува",
    69670: "Ошибка создания кабинета, неверный email",
    74839: "до 30/06 Проблема после já foi",
    83903: "Первичное ВНЖ из Одивелаш/Авейру",
    122138: "Дозапросы",
}

MAIN_TOPIC = 43114
GENERAL_TOPIC = 1

# Поля, которые вытаскиваем из result.json. reply нужен для определения топика.
#
# links — адреса гиперссылок (entity `text_link`). Без них URL, спрятанный под
# текстом («вот страница инициативы»), в экспорте виден только как этот текст, и
# поиск по домену его не находит. Так однажды «потерялась» ссылка на
# parlamento.pt, которая всё время лежала в процитированном сообщении.
#
# media — вложение (скриншот, PDF). Много ценного в чате показано картинкой:
# бланк сертификата, текст отказа, экраны портала. В тексте от такого сообщения
# остаётся в лучшем случае подпись, поэтому поиском они не находятся — нужен
# отдельный признак. Значение — путь к файлу внутри каталога экспорта либо
# заглушка «(File not included…)», если медиа не выгружали.
JQ_FILTER = (
    '.messages[] | select(.type=="message") | '
    "{id, date, from, reply: .reply_to_message_id, "
    'text: ([.text_entities[].text] | join("")), '
    "links: [.text_entities[] | select(.href) | .href], "
    "media: (.photo // .file), "
    "media_name: (.file_name // .media_type // (if .photo then \"photo\" else null end))}"
)

# Меняется при правке JQ_FILTER — иначе останется старый кэш без новых полей.
CACHE_VERSION = 3

_msgs: dict[int, dict] = {}
_topic_ids: set[int] = set()


def _find_exports(pattern: str) -> list[pathlib.Path]:
    """
    Все result.json, подходящие под маску (имена каталогов содержат дату).

    Экспортов одного вида может быть несколько: полный выгружается редко, а
    доклад свежего материала удобнее делать частичным («past month» — 13 МБ
    против 279 МБ). Они склеиваются в один индекс, поздние сообщения
    перекрывают ранние (правки текста), см. _load_exports().
    """
    found = sorted(EXPORT_DIR.glob(f"{pattern}/result.json"))
    if not found:
        sys.exit(
            f"❌ Не найден экспорт '{pattern}' в {EXPORT_DIR}.\n"
            "   Экспорт истории чата не хранится в репозитории (перс. данные)."
        )
    return found


def _extract(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Извлечь JSONL из result.json, если кэш отсутствует или устарел."""
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return
    if not shutil.which("jq"):
        sys.exit("❌ Нужен jq (sudo apt install jq).")
    print(f"▶ Строю кэш {dst.name} из {src.parent.name}…", file=sys.stderr)
    dst.parent.mkdir(exist_ok=True)
    with dst.open("w", encoding="utf-8") as out:
        subprocess.run(["jq", "-c", JQ_FILTER, str(src)], stdout=out, check=True)


def _load_exports(pattern: str, prefix: str) -> dict[int, dict]:
    """Склеить все экспорты по маске в один индекс id → сообщение."""
    out: dict[int, dict] = {}
    for src in _find_exports(pattern):
        dst = CACHE_DIR / f"{prefix}-v{CACHE_VERSION}-{src.parent.name}.jsonl"
        _extract(src, dst)
        for line in dst.read_text(encoding="utf-8").splitlines():
            m = json.loads(line)
            # Путь к вложению — относительно каталога экспорта, а он известен
            # только здесь. Файл есть не всегда: в полном экспорте медиа не
            # выгружали, там вместо пути стоит «(File not included…)».
            media = m.get("media")
            if media:
                path = src.parent / media
                m["media_path"] = str(path) if path.exists() else None
            out[m["id"]] = m
    return out


def load() -> dict[int, dict]:
    """Загрузить сообщения полных экспортов (с кэшированием). id → сообщение."""
    global _msgs, _topic_ids
    if _msgs:
        return _msgs

    _msgs = _load_exports("Export all *", "all")

    # Экспорт одного топика — страховка для определения топика, см. root_of().
    _topic_ids = set(_load_exports('Export "После 30.06.2025"*', "topic"))
    return _msgs


def root_of(mid: int) -> int:
    """
    Определить топик сообщения подъёмом по цепочке reply_to_message_id.

    У сообщения верхнего уровня внутри ветки reply указывает на id самого
    топика, поэтому подъём рано или поздно упирается в известный топик.

    Цепочка, оборвавшаяся на сообщении **без** reply, означает General: внутри
    ветки такого не бывает. Проверено по экспорту ветки 43114 — из 46 412
    сообщений с такой цепочкой в ней нет ни одного.

    ⚠️ Цепочка рвётся, если родительское сообщение отсутствует в экспорте
    (удалено; в частичном экспорте — вышло за период). Тогда топик неизвестен:
    для основного топика это лечится проверкой по отдельному экспорту ветки,
    для остальных страховки нет — результат стоит перепроверить глазами.
    Таких сообщений мало (3 207 из 146 641 в экспортах на 27.07.2026).
    """
    load()
    seen: set[int] = set()
    cur = mid
    while True:
        if cur in TOPICS:
            return cur
        m = _msgs.get(cur)
        if m is None or cur in seen:  # родитель не в экспорте / цикл
            return MAIN_TOPIC if mid in _topic_ids else cur
        if m.get("reply") is None:  # верх цепочки вне ветки — значит General
            return MAIN_TOPIC if mid in _topic_ids else GENERAL_TOPIC
        seen.add(cur)
        cur = m["reply"]


def link(mid: int) -> str:
    """Ссылка на сообщение. Без известного топика — короткая форма."""
    root = root_of(mid)
    if root in TOPICS:
        return f"https://t.me/aimairn/{root}/{mid}"
    return f"https://t.me/aimairn/{mid}"


def replies_to(mid: int) -> list[dict]:
    """
    Прямые ответы на сообщение, в хронологическом порядке.

    Нужно, когда в чате процитирован вопрос: ответ на него — отдельное
    сообщение, и без него в вики попадёт «вопрос без ответа».
    """
    msgs = load()
    hits = [m for m in msgs.values() if m.get("reply") == mid]
    hits.sort(key=lambda m: m["date"])
    return hits


def search(pattern, topic=None, min_len=0, max_len=None, media=False):
    """
    Сообщения, подходящие под регэксп/фильтры, в хронологическом порядке.

    Регэксп проверяется и по адресам гиперссылок, а не только по видимому
    тексту: искать домен или номер документа в URL — обычное дело.

    media=True оставляет только сообщения с вложением. Пустой регэксп при этом
    осмыслен: «покажи все картинки вокруг такого-то периода» — обычный способ
    найти скриншот, у которого нет подписи.
    """
    msgs = load()
    pat = re.compile(pattern, re.I)
    hits = [
        m for m in msgs.values()
        if len(m["text"]) >= min_len
        and (max_len is None or len(m["text"]) <= max_len)
        and (topic is None or root_of(m["id"]) == topic)
        and (not media or m.get("media"))
        and (pat.search(m["text"]) or any(pat.search(u) for u in m.get("links", ())))
    ]
    hits.sort(key=lambda m: m["date"])
    return hits


def link_inventory(domain_pattern: str | None = None) -> list[tuple[str, list[dict]]]:
    """
    Инвентарь адресов гиперссылок: URL → сообщения, где он встречается.

    Нужен для ревизии «что из чата ещё не перенесено в вики»: такие ссылки в
    тексте не видны (они спрятаны под словами), и глазами их не выловить.
    Сортировка — по числу упоминаний: чем чаще ссылку давали, тем вероятнее она
    полезна читателю.
    """
    msgs = load()
    pat = re.compile(domain_pattern, re.I) if domain_pattern else None
    urls: dict[str, list[dict]] = {}
    for m in msgs.values():
        for url in dict.fromkeys(m.get("links", ())):
            if pat is None or pat.search(url):
                urls.setdefault(url, []).append(m)
    for hits in urls.values():
        hits.sort(key=lambda m: m["date"])
    return sorted(urls.items(), key=lambda kv: (-len(kv[1]), kv[0]))


def _show(m: dict, chars: int) -> None:
    root = root_of(m["id"])
    name = TOPICS.get(root, "топик неизвестен")
    print(f"--- #{m['id']} | {m['date'][:10]} | {name} | {link(m['id'])}")
    text = m["text"]
    print(text[:chars] + ("…" if len(text) > chars else ""))
    # Адреса гиперссылок — в тексте их не видно, а они часто и есть суть находки.
    for url in dict.fromkeys(m.get("links", ())):
        print(f"    🔗 {url}")
    if m.get("media"):
        where = m.get("media_path") or "файл не выгружен — смотреть по ссылке"
        print(f"    📎 {m.get('media_name') or 'вложение'}: {where}")
    print()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Поиск по экспорту чата с готовыми ссылками на сообщения.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Топики: " + ", ".join(f"{k}={v}" for k, v in TOPICS.items()),
    )
    p.add_argument("pattern", nargs="?", help="регэксп (регистр игнорируется)")
    p.add_argument("--id", type=int, help="показать одно сообщение целиком")
    p.add_argument("--replies", type=int, metavar="ID", help="ответы на это сообщение")
    p.add_argument("--topic", type=int, help="только эта ветка (id из списка ниже)")
    p.add_argument("--min-len", type=int, default=0, help="от N символов (гайды — от 600)")
    p.add_argument("--max-len", type=int, help="до N символов")
    p.add_argument("--media", action="store_true", help="только сообщения с вложением")
    p.add_argument("--limit", type=int, default=25, help="сколько показать (0 = все)")
    p.add_argument("--chars", type=int, default=2000, help="сколько символов текста")
    p.add_argument(
        "--links",
        nargs="?",
        const="",
        metavar="РЕГЭКСП",
        help="инвентарь адресов гиперссылок (можно сузить регэкспом по URL)",
    )
    args = p.parse_args()

    if args.links is not None:
        inv = link_inventory(args.links or None)
        print(f"### уникальных адресов: {len(inv)}\n")
        for url, hits in inv:
            first, last = hits[0], hits[-1]
            period = first["date"][:10]
            if last is not first:
                period += f" … {last['date'][:10]}"
            print(f"{len(hits):3d}×  {url}")
            print(f"      {period} | {link(first['id'])}")
        return 0

    if args.id:
        m = load().get(args.id)
        if not m:
            print(f"Сообщение #{args.id} не найдено в экспорте.", file=sys.stderr)
            return 1
        _show(m, 10**9)
        return 0

    if args.replies:
        hits = replies_to(args.replies)
        print(f"### ответов на #{args.replies}: {len(hits)}\n")
        for m in hits:
            _show(m, args.chars)
        return 0

    if not args.pattern and not args.media:
        p.error("нужен регэксп, либо --media, либо --id, либо --replies")

    hits = search(args.pattern or "", args.topic, args.min_len, args.max_len, args.media)
    shown = hits if args.limit == 0 else hits[: args.limit]
    print(f"### найдено: {len(hits)} (показано {len(shown)})\n")
    for m in shown:
        _show(m, args.chars)
    return 0


if __name__ == "__main__":
    sys.exit(main())
