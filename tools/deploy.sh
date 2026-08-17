#!/usr/bin/env bash
# Заливка dist/ на Cloudflare Pages (Direct Upload).
#
#   tools/deploy.sh              — залить в продакшн
#   tools/deploy.sh --preview    — залить как превью, отдельной веткой
#
# Токен и account_id берутся из .env в корне проекта. Это аккаунт ЗАКАЗЧИКА —
# не путать с личным в ~/AKcf.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="${PAGES_PROJECT:-tpi-lux}"
DIST="$ROOT/dist"

die() { echo "Ошибка: $*" >&2; exit 1; }

# --- окружение -------------------------------------------------------------
# wrangler живёт на Node 20 из nvm. Системный Node 18 для него слишком стар,
# поэтому путь подставляется явно, а не берётся из PATH.
NVM_NODE="$HOME/.nvm/versions/node/v20.20.2/bin"
[ -d "$NVM_NODE" ] || die "нет Node 20 в $NVM_NODE — поставить: nvm install 20"
export PATH="$NVM_NODE:$PATH"
command -v wrangler >/dev/null || die "нет wrangler — поставить: npm i -g wrangler@4"

[ -f "$ROOT/.env" ] || die "нет $ROOT/.env — скопировать из .env.example и вписать токен"
perms=$(stat -c '%a' "$ROOT/.env")
[ "$perms" = "600" ] || { chmod 600 "$ROOT/.env"; echo "(поправил права .env: $perms → 600)" >&2; }
set -a; . "$ROOT/.env"; set +a
[ -n "${CLOUDFLARE_API_TOKEN:-}" ] || die "CLOUDFLARE_API_TOKEN пуст в .env"

# account_id: из .env, иначе вытащить и запомнить
if [ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]; then
  CLOUDFLARE_ACCOUNT_ID=$(curl -sS --ipv4 https://api.cloudflare.com/client/v4/accounts \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq -r '.result[0].id // empty')
  [ -n "$CLOUDFLARE_ACCOUNT_ID" ] || die "не смог определить account_id — нужно право Account Settings:Read"
  sed -i "s|^CLOUDFLARE_ACCOUNT_ID=.*|CLOUDFLARE_ACCOUNT_ID=$CLOUDFLARE_ACCOUNT_ID|" "$ROOT/.env"
  echo "Записал CLOUDFLARE_ACCOUNT_ID=$CLOUDFLARE_ACCOUNT_ID в .env"
fi
export CLOUDFLARE_ACCOUNT_ID

# --- сборка ----------------------------------------------------------------
[ -d "$DIST" ] || die "нет $DIST — собрать: python3 tools/build.py"
files=$(find "$DIST" -type f | wc -l)
[ "$files" -gt 0 ] || die "$DIST пуст"
# У Pages лимиты Direct Upload: 20000 файлов, 25 МиБ на файл.
big=$(find "$DIST" -type f -size +25M | head -1)
[ -z "$big" ] || die "файл больше 25 МиБ, Pages его не примет: $big"
echo "К заливке: $files файлов, $(du -sh "$DIST" | cut -f1)"

# --- проект ----------------------------------------------------------------
# Если проекта ещё нет, создать. Отдельный шаг: wrangler в неинтерактивном
# режиме сам его не заводит, а падает с невнятной ошибкой.
if ! wrangler pages project list 2>/dev/null | grep -qw "$PROJECT"; then
  echo "Проекта '$PROJECT' нет — создаю…"
  wrangler pages project create "$PROJECT" --production-branch=main
fi

# --- заливка ---------------------------------------------------------------
BRANCH=main
if [ "${1:-}" = "--preview" ]; then
  BRANCH="preview"
  echo "Режим превью: отдельная ветка '$BRANCH', продакшн не затрагивается."
fi

wrangler pages deploy "$DIST" \
  --project-name="$PROJECT" \
  --branch="$BRANCH" \
  --commit-dirty=true
