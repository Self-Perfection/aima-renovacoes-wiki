#!/usr/bin/env python3
"""
check_wiki.py — проверки содержимого вики, которые не делает mkdocs.

Что проверяет:
  1. У каждой страницы есть `description:` во front matter — иначе в превью
     ссылки (Telegram, Slack) подставится общее описание сайта, одинаковое
     для всех страниц.
  2. Ссылки на сообщения чата ведут в правильную ветку: сообщение существует
     в экспорте, и вычисленный по нему топик совпадает с тем, что в URL.

Проверка ссылок требует экспорта чата (`Чат продления ВНЖ/`, в .gitignore).
Если его нет — этот шаг пропускается, а не падает: вики должна собираться и
без приватных данных.

Использование:  tools/check_wiki.py
Код возврата:   0 — всё чисто, 1 — есть проблемы.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"

# Ссылка на сообщение внутри ветки: t.me/aimairn/<topic>/<msg>
MSG_LINK = re.compile(r"https://t\.me/aimairn/(\d+)/(\d+)")
# Рекомендуемая длина описания: длиннее — обрежется в превью.
DESC_MAX = 200


def pages():
    """Страницы вики (без Zim-симлинков *.md.md)."""
    return sorted(p for p in WIKI.rglob("*.md") if not p.name.endswith(".md.md"))


def check_descriptions() -> list[str]:
    problems = []
    for p in pages():
        text = p.read_text(encoding="utf-8")
        rel = p.relative_to(ROOT)
        if not text.startswith("---\n"):
            problems.append(f"нет front matter с description: {rel}")
            continue
        head = text[: text.index("\n---\n", 3)]
        m = re.search(r'^description:\s*"?(.*?)"?\s*$', head, re.M)
        if not m:
            problems.append(f"нет description: {rel}")
        elif len(m.group(1)) > DESC_MAX:
            problems.append(
                f"description длиннее {DESC_MAX} символов ({len(m.group(1))}): {rel}"
            )
    return problems


def check_message_links() -> list[str]:
    sys.path.insert(0, str(ROOT / "tools"))
    import chat

    if not chat.EXPORT_DIR.exists():
        print("⚠  Экспорт чата недоступен — проверка ссылок ПРОПУЩЕНА.")
        return None

    msgs = chat.load()
    problems = []
    total = 0
    for p in pages():
        rel = p.relative_to(ROOT)
        for topic_s, mid_s in MSG_LINK.findall(p.read_text(encoding="utf-8")):
            total += 1
            topic, mid = int(topic_s), int(mid_s)
            if mid == topic:
                continue  # ссылка на саму ветку, а не на сообщение в ней
            if mid not in msgs:
                problems.append(f"сообщения #{mid} нет в экспорте: {rel}")
            elif (real := chat.root_of(mid)) != topic:
                problems.append(
                    f"#{mid} лежит в ветке {real}, а ссылка ведёт в {topic}: {rel}"
                )
    print(f"▶ Проверено ссылок на сообщения: {total}")
    return problems


def main() -> int:
    links = check_message_links()  # None, если экспорт недоступен
    problems = check_descriptions() + (links or [])
    if problems:
        print(f"\n❌ Проблем: {len(problems)}")
        for x in problems:
            print(f"   {x}")
        return 1
    checked = "Описания страниц и ссылки на сообщения" if links is not None \
        else "Описания страниц (только они)"
    print(f"✅ {checked} — в порядке.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
