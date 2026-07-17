# Вики: продление ВНЖ Португалии через портал AIMA

Народный справочник по продлению ВНЖ (título de residência) Португалии через
портал **AIMA Renovações** (`portal-renovacoes.aima.gov.pt`) — для тех, чей ВНЖ
истекает **после 30.06.2025**. Собран из опыта русскоязычного Telegram-сообщества
[«Продление ВНЖ»](https://t.me/aimairn) (топик [«После 30.06.2025»](https://t.me/aimairn/43114)).

📖 **Читать сайт:** https://self-perfection.github.io/aima-renovacoes-wiki/

> ⚠️ Не официальный ресурс AIMA. Информация получена опытным путём, может
> содержать ошибки и устаревать. Сверяйтесь с [aima.gov.pt](https://aima.gov.pt).

## Структура

Исходники — Markdown в каталоге [`wiki/`](wiki/), сгруппированы по разделам:
`process/` · `prerequisites/` · `problems/` · `special/` · `reference/`.
Навигация и рендеринг — через [MkDocs](https://www.mkdocs.org/) + тему
[Material](https://squidfunk.github.io/mkdocs-material/).

## Локальная сборка

```bash
pip install mkdocs-material
mkdocs serve      # локальный предпросмотр на http://127.0.0.1:8000
mkdocs build      # сборка статики в ./site
```

## Публикация

Сайт публикуется на GitHub Pages из ветки `gh-pages`:

```bash
mkdocs gh-deploy --force
```

## Совместимость с Zim

Каталог `wiki/` можно открывать и в [Zim Desktop Wiki](https://zim-wiki.org/)
(файл `notebook.zim`). Для его экспериментального markdown-режима рядом с каждой
страницей лежат локальные симлинки `*.md.md` — они в `.gitignore` и не попадают ни
в репозиторий, ни в сборку MkDocs.

## Лицензия / источники

Ссылки в статьях ведут на конкретные сообщения публичного чата
(`https://t.me/aimairn/43114/<id>`). Имена авторов не указываются.
