#!/usr/bin/env bash
#
# release.sh — пересборка и публикация вики (MkDocs → GitHub Pages).
#
# Что делает:
#   1) регенерирует локальные Zim-симлинки (*.md.md, в .gitignore);
#   2) валидирует сборку `mkdocs build --strict` (падает на битых ссылках/nav);
#   3) если есть незакоммиченные изменения — коммитит их (нужно сообщение) и пушит main;
#   4) деплоит сайт в ветку gh-pages (`mkdocs gh-deploy --force`);
#   5) проверяет, что сайт отвечает 200.
#
# Использование:
#   ./release.sh "что изменилось"   # с коммитом изменений
#   ./release.sh                    # если исходники уже закоммичены — просто передеплой
#
set -euo pipefail

cd "$(dirname "$0")"

SITE_URL="https://self-perfection.github.io/aima-renovacoes-wiki/"
MSG="${1:-}"

# --- проверки окружения ---
command -v git    >/dev/null || { echo "❌ git не установлен";  exit 1; }
command -v mkdocs >/dev/null || { echo "❌ mkdocs не установлен (sudo apt install mkdocs-material)"; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { echo "❌ не git-репозиторий (или проблема доступа: git config --global --add safe.directory \"$(pwd)\")"; exit 1; }

# --- 1. Zim-симлинки (локально; в .gitignore и в сборку MkDocs не идут) ---
echo "▶ Регенерация Zim-симлинков…"
( cd wiki
  find . -name '*.md.md' -delete
  find . -name '*.md' ! -name '*.md.md' -print0 |
    while IFS= read -r -d '' f; do ln -sf "$(basename "$f")" "$f.md"; done )

# --- 2. Валидация сборки ---
echo "▶ Проверка сборки (mkdocs build --strict)…"
mkdocs build --strict

# --- 2b. Описания страниц и ссылки на сообщения чата ---
# (ссылки проверяются только если под рукой экспорт чата — он не в репозитории)
echo "▶ Проверка описаний и ссылок на сообщения…"
./tools/check_wiki.py

# --- 3. Коммит и пуш исходников ---
if [ -n "$(git status --porcelain)" ]; then
  if [ -z "$MSG" ]; then
    echo "❌ Есть незакоммиченные изменения. Укажите сообщение коммита:"
    echo "   ./release.sh \"что изменилось\""
    exit 1
  fi
  echo "▶ Коммит изменений…"
  git add -A
  git commit -m "$MSG"
else
  echo "▶ Изменений в исходниках нет — коммит пропущен."
fi

echo "▶ Пуш main…"
git push origin main

# --- 4. Деплой на GitHub Pages ---
echo "▶ Деплой в gh-pages…"
mkdocs gh-deploy --force

# --- 5. Проверка доступности ---
echo "▶ Проверка сайта…"
code="$(curl -fsS -o /dev/null -w '%{http_code}' --retry 15 --retry-delay 6 --retry-all-errors "$SITE_URL" || true)"
if [ "$code" = "200" ]; then
  echo "✅ Опубликовано: $SITE_URL"
else
  echo "⚠  Сайт вернул HTTP $code — GitHub Pages может ещё собираться, проверьте через минуту: $SITE_URL"
fi
