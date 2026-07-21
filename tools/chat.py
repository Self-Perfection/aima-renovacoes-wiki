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

# Поля, которые вытаскиваем из result.json. reply нужен для определения топика.
JQ_FILTER = (
    '.messages[] | select(.type=="message") | '
    "{id, date, from, reply: .reply_to_message_id, "
    'text: ([.text_entities[].text] | join(""))}'
)

_msgs: dict[int, dict] = {}
_topic_ids: set[int] = set()


def _find_export(pattern: str) -> pathlib.Path:
    """Найти result.json нужного экспорта (имена каталогов содержат дату)."""
    found = sorted(EXPORT_DIR.glob(f"{pattern}/result.json"))
    if not found:
        sys.exit(
            f"❌ Не найден экспорт '{pattern}' в {EXPORT_DIR}.\n"
            "   Экспорт истории чата не хранится в репозитории (перс. данные)."
        )
    return found[-1]


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


def load() -> dict[int, dict]:
    """Загрузить сообщения полного экспорта (с кэшированием). id → сообщение."""
    global _msgs, _topic_ids
    if _msgs:
        return _msgs

    all_jsonl = CACHE_DIR / "all.jsonl"
    _extract(_find_export("Export all *"), all_jsonl)
    for line in all_jsonl.read_text(encoding="utf-8").splitlines():
        m = json.loads(line)
        _msgs[m["id"]] = m

    # Экспорт одного топика — страховка для определения топика, см. root_of().
    topic_jsonl = CACHE_DIR / f"topic-{MAIN_TOPIC}.jsonl"
    _extract(_find_export('Export "После 30.06.2025"*'), topic_jsonl)
    _topic_ids = {
        json.loads(line)["id"]
        for line in topic_jsonl.read_text(encoding="utf-8").splitlines()
    }
    return _msgs


def root_of(mid: int) -> int:
    """
    Определить топик сообщения подъёмом по цепочке reply_to_message_id.

    У сообщения верхнего уровня внутри ветки reply указывает на id самого
    топика, поэтому подъём рано или поздно упирается в известный топик.

    ⚠️ Цепочка рвётся, если родительское сообщение удалено (его нет в
    экспорте). Для основного топика это лечится проверкой по отдельному
    экспорту ветки; для остальных топиков страховки нет — результат стоит
    перепроверить глазами.
    """
    load()
    seen: set[int] = set()
    cur = mid
    while True:
        if cur in TOPICS:
            return cur
        m = _msgs.get(cur)
        if m is None or m.get("reply") is None or cur in seen:
            return MAIN_TOPIC if mid in _topic_ids else cur
        seen.add(cur)
        cur = m["reply"]


def link(mid: int) -> str:
    """Ссылка на сообщение. Без известного топика — короткая форма."""
    root = root_of(mid)
    if root in TOPICS:
        return f"https://t.me/aimairn/{root}/{mid}"
    return f"https://t.me/aimairn/{mid}"


def search(pattern, topic=None, min_len=0, max_len=None):
    """Сообщения, подходящие под регэксп/фильтры, в хронологическом порядке."""
    msgs = load()
    pat = re.compile(pattern, re.I)
    hits = [
        m for m in msgs.values()
        if len(m["text"]) >= min_len
        and (max_len is None or len(m["text"]) <= max_len)
        and (topic is None or root_of(m["id"]) == topic)
        and pat.search(m["text"])
    ]
    hits.sort(key=lambda m: m["date"])
    return hits


def _show(m: dict, chars: int) -> None:
    root = root_of(m["id"])
    name = TOPICS.get(root, "топик неизвестен")
    print(f"--- #{m['id']} | {m['date'][:10]} | {name} | {link(m['id'])}")
    text = m["text"]
    print(text[:chars] + ("…" if len(text) > chars else ""))
    print()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Поиск по экспорту чата с готовыми ссылками на сообщения.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Топики: " + ", ".join(f"{k}={v}" for k, v in TOPICS.items()),
    )
    p.add_argument("pattern", nargs="?", help="регэксп (регистр игнорируется)")
    p.add_argument("--id", type=int, help="показать одно сообщение целиком")
    p.add_argument("--topic", type=int, help="только эта ветка (id из списка ниже)")
    p.add_argument("--min-len", type=int, default=0, help="от N символов (гайды — от 600)")
    p.add_argument("--max-len", type=int, help="до N символов")
    p.add_argument("--limit", type=int, default=25, help="сколько показать (0 = все)")
    p.add_argument("--chars", type=int, default=2000, help="сколько символов текста")
    args = p.parse_args()

    if args.id:
        m = load().get(args.id)
        if not m:
            print(f"Сообщение #{args.id} не найдено в экспорте.", file=sys.stderr)
            return 1
        _show(m, 10**9)
        return 0

    if not args.pattern:
        p.error("нужен либо регэксп, либо --id")

    hits = search(args.pattern, args.topic, args.min_len, args.max_len)
    shown = hits if args.limit == 0 else hits[: args.limit]
    print(f"### найдено: {len(hits)} (показано {len(shown)})\n")
    for m in shown:
        _show(m, args.chars)
    return 0


if __name__ == "__main__":
    sys.exit(main())
