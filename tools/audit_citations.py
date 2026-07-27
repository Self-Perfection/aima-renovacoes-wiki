#!/usr/bin/env python3
"""
audit_citations.py — свести каждую ссылку на сообщение с текстом самого сообщения.

Зачем: вики должна быть самодостаточным руководством. Ссылка на сообщение — это
подтверждение источника, а не замена содержания: читатель не обязан идти в чат,
чтобы узнать, что делать. Проверить это глазами трудно — контекст цитаты лежит в
`wiki/`, а текст сообщения в 130-МБ экспорте. Скрипт печатает их рядом.

    tools/audit_citations.py                      # весь отчёт
    tools/audit_citations.py wiki/process         # только эти страницы
    tools/audit_citations.py --chars 3000         # длиннее показывать сообщения
    tools/audit_citations.py --context 6          # шире контекст в вики

Формат: для каждой страницы — цитаты в порядке чтения; у каждой цитаты абзац
вики, где она стоит, и текст сообщения-источника. Повторные цитаты того же
сообщения текст не дублируют.

Читать отчёт так: если в абзаце вики есть инструкция из сообщения — хорошо;
если вики отсылает «см. #NNN» за самой инструкцией — содержимое надо перенести.
Кейсы, таймлайны и примеры переносить не нужно, им место в чате.
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
WIKI = ROOT / "wiki"
sys.path.insert(0, str(ROOT / "tools"))

MSG_LINK = re.compile(r"https://t\.me/aimairn/(\d+)/(\d+)")


def pages(targets: list[str]) -> list[pathlib.Path]:
    """Страницы вики (без Zim-симлинков *.md.md), опционально по путям."""
    roots = [pathlib.Path(t).resolve() for t in targets] or [WIKI]
    found: set[pathlib.Path] = set()
    for r in roots:
        found.update(p for p in ([r] if r.is_file() else r.rglob("*.md"))
                     if p.suffix == ".md" and not p.name.endswith(".md.md"))
    return sorted(found)


def blocks(text: str) -> list[tuple[int, str]]:
    """Абзацы файла как (номер первой строки, текст) — контекст цитаты."""
    out, start, buf = [], 1, []
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip():
            if not buf:
                start = n
            buf.append(line)
        elif buf:
            out.append((start, "\n".join(buf)))
            buf = []
    if buf:
        out.append((start, "\n".join(buf)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="страницы/каталоги (по умолчанию вся вики)")
    ap.add_argument("--chars", type=int, default=1800, help="символов текста сообщения")
    args = ap.parse_args()

    import chat
    if not chat.EXPORT_DIR.exists():
        sys.exit("❌ Нужен экспорт чата — без него сверять не с чем.")
    msgs = chat.load()

    seen: dict[int, str] = {}  # id → где процитировано впервые
    n_cites = 0
    for page in pages(args.paths):
        rel = page.relative_to(ROOT)
        text = page.read_text(encoding="utf-8")
        if not MSG_LINK.search(text):
            continue
        print(f"\n{'=' * 78}\n## {rel}\n{'=' * 78}")
        for line_no, block in blocks(text):
            ids = [int(m) for _, m in MSG_LINK.findall(block)]
            if not ids:
                continue
            print(f"\n--- {rel}:{line_no} — контекст вики "
                  f"({len(ids)} ссыл.) {'-' * 20}\n{block}\n")
            for mid in dict.fromkeys(ids):
                n_cites += 1
                if mid in seen:
                    print(f"    [#{mid} — текст выше, {seen[mid]}]")
                    continue
                seen[mid] = f"{rel}:{line_no}"
                m = msgs.get(mid)
                if m is None:
                    print(f"    [#{mid} — НЕТ В ЭКСПОРТЕ]")
                    continue
                body = m["text"][: args.chars]
                if len(m["text"]) > args.chars:
                    body += f"… (ещё {len(m['text']) - args.chars} симв.)"
                print(f"    ┌─ #{mid} | {m['date'][:10]} | {chat.link(mid)}")
                for ln in body.splitlines() or [""]:
                    print(f"    │ {ln}")
                print("    └─")

    print(f"\n{'=' * 78}\nЦитат: {n_cites}, уникальных сообщений: {len(seen)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
