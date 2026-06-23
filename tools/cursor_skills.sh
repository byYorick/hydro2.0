#!/usr/bin/env bash
# Установка и проверка Cursor Agent Skills для hydro2.0
# Внешние skills: npx skills add → .agents/skills/ + skills-lock.json
# Проектные skills: .claude/skills/ (Cursor подхватывает автоматически)
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

SKILLS_LOCK="$PROJECT_ROOT/skills-lock.json"
AGENTS_SKILLS_DIR="$PROJECT_ROOT/.agents/skills"
CLAUDE_SKILLS_DIR="$PROJECT_ROOT/.claude/skills"

# --- Манифест внешних skills (репозиторий:имена через пробел) ---
AWESOME_REPO="thienanblog/awesome-ai-agent-skills"
AWESOME_SKILLS=(
  laravel-11-12-app-guidelines
  docker-local-dev
  documentation-guidelines
)

CURSOR_PLUGINS_REPO="cursor/plugins"
CURSOR_TEAM_SKILLS=(
  fix-ci
  get-pr-comments
  loop-on-ci
  review-and-ship
  run-smoke-tests
)

ESP_FIRMWARE_REPO="adamlipecz/esp32-firmware-engineer-skill"
ESP_FIRMWARE_SKILLS=(
  esp32-firmware-engineer
)

EMBEDDED_REPO="jeffallan/claude-skills"
EMBEDDED_SKILLS=(
  embedded-systems
)

MCP_CONFIG="$PROJECT_ROOT/.cursor/mcp.json"

# Обязательные MCP-серверы в .cursor/mcp.json (ключ → описание для cmd_list)
MCP_MANIFEST=(
  "espressif-docs|remote|ESP-IDF документация (OAuth: GitHub/WeChat)"
  "esp-component-registry|remote|ESP Component Registry"
  "mqtt|stdio|Dev MQTT broker localhost:1883 (топики hydro/#)"
  "postgres|stdio|PostgreSQL hydro_dev (restricted, docker)"
  "redis|stdio|Redis dev :6379 (docker)"
  "laravel-boost|stdio|Laravel Boost MCP (backend/laravel)"
)

# Проектные skills (директории относительно PROJECT_ROOT)
PROJECT_SKILL_DIRS=(
  .claude/skills/two-tank-debug
)

log() { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require_npx() {
  if ! command -v npx >/dev/null 2>&1; then
    die "npx не найден. Установи Node.js (например fnm/nvm) или запусти: make dev-tools-install"
  fi
}

all_external_skills() {
  printf '%s\n' \
    "${AWESOME_SKILLS[@]}" \
    "${CURSOR_TEAM_SKILLS[@]}" \
    "${ESP_FIRMWARE_SKILLS[@]}" \
    "${EMBEDDED_SKILLS[@]}"
}

validate_skill_md() {
  local skill_md="$1"
  local label="$2"

  [[ -f "$skill_md" ]] || { warn "нет SKILL.md: $label"; return 1; }

  local ok=0
  grep -q '^---$' "$skill_md" || ok=1
  grep -qE '^name:[[:space:]]*[^[:space:]]' "$skill_md" || ok=1
  grep -qE '^description:[[:space:]]*.+' "$skill_md" || ok=1

  if [[ "$ok" -ne 0 ]]; then
    warn "невалидный frontmatter в $skill_md"
    return 1
  fi

  return 0
}

check_skill_dir() {
  local dir="$1"
  local label="$2"
  validate_skill_md "$dir/SKILL.md" "$label"
}

cmd_list() {
  echo "hydro2.0 — манифест Cursor skills"
  echo ""
  echo "Внешние ($AWESOME_REPO):"
  for s in "${AWESOME_SKILLS[@]}"; do echo "  - $s"; done
  echo ""
  echo "Внешние ($CURSOR_PLUGINS_REPO / cursor-team-kit):"
  for s in "${CURSOR_TEAM_SKILLS[@]}"; do echo "  - $s"; done
  echo ""
  echo "Внешние ($ESP_FIRMWARE_REPO):"
  for s in "${ESP_FIRMWARE_SKILLS[@]}"; do echo "  - $s"; done
  echo ""
  echo "Внешние ($EMBEDDED_REPO):"
  for s in "${EMBEDDED_SKILLS[@]}"; do echo "  - $s"; done
  echo ""
  echo "Проектные (.claude/skills/):"
  for d in "${PROJECT_SKILL_DIRS[@]}"; do echo "  - $d"; done
  echo ""

  if [[ -f "$SKILLS_LOCK" ]] && command -v jq >/dev/null 2>&1; then
    echo "Установлено (skills-lock.json):"
    jq -r '.skills | keys[]' "$SKILLS_LOCK" 2>/dev/null | sed 's/^/  - /' || true
  elif [[ -d "$AGENTS_SKILLS_DIR" ]]; then
    echo "Установлено (.agents/skills/):"
    find "$AGENTS_SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d -printf '  - %f\n' 2>/dev/null \
      || find "$AGENTS_SKILLS_DIR" -mindepth 1 -maxdepth 1 -type d | sed 's|.*/|  - |'
  else
    echo "Внешние skills ещё не установлены. Запусти: make skills-install"
  fi
}

cmd_install() {
  require_npx
  mkdir -p "$AGENTS_SKILLS_DIR"

  log "Установка Laravel/Docker/docs skills из $AWESOME_REPO"
  local awesome_args=()
  for s in "${AWESOME_SKILLS[@]}"; do awesome_args+=(--skill "$s"); done
  npx --yes skills add "$AWESOME_REPO" \
    "${awesome_args[@]}" \
    --agent cursor \
    --copy \
    -y

  log "Установка cursor-team-kit skills из $CURSOR_PLUGINS_REPO"
  local team_args=()
  for s in "${CURSOR_TEAM_SKILLS[@]}"; do team_args+=(--skill "$s"); done
  npx --yes skills add "$CURSOR_PLUGINS_REPO" \
    "${team_args[@]}" \
    --agent cursor \
    --copy \
    -y

  log "Установка ESP-IDF firmware skills из $ESP_FIRMWARE_REPO"
  local esp_args=()
  for s in "${ESP_FIRMWARE_SKILLS[@]}"; do esp_args+=(--skill "$s"); done
  npx --yes skills add "$ESP_FIRMWARE_REPO" \
    "${esp_args[@]}" \
    --agent cursor \
    --copy \
    -y

  log "Установка embedded skills из $EMBEDDED_REPO"
  local embedded_args=()
  for s in "${EMBEDDED_SKILLS[@]}"; do embedded_args+=(--skill "$s"); done
  npx --yes skills add "$EMBEDDED_REPO" \
    "${embedded_args[@]}" \
    --agent cursor \
    --copy \
    -y

  log "Установка/обновление .cursor/mcp.json"
  ensure_project_mcp

  log "Проверка после установки"
  cmd_check
}

write_project_mcp_json_to_file() {
  local dest="$1"
  cat >"$dest" <<'EOF'
{
  "mcpServers": {
    "espressif-docs": {
      "url": "https://mcp.espressif.com/docs"
    },
    "esp-component-registry": {
      "url": "https://components.espressif.com/mcp"
    },
    "mqtt": {
      "command": "uvx",
      "args": [
        "--from",
        "mqtt-mcp-server",
        "python",
        "-m",
        "mqtt_mcp.server"
      ],
      "env": {
        "MQTT_HOST": "127.0.0.1",
        "MQTT_PORT": "1883"
      }
    },
    "postgres": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "--network",
        "host",
        "crystaldba/postgres-mcp",
        "--access-mode",
        "restricted",
        "postgresql://hydro:hydro@127.0.0.1:5432/hydro_dev"
      ]
    },
    "redis": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "--network",
        "host",
        "mcp/redis",
        "uv",
        "run",
        "redis-mcp-server",
        "--url",
        "redis://127.0.0.1:6379/0"
      ]
    },
    "laravel-boost": {
      "command": "php",
      "args": [
        "artisan",
        "boost:mcp"
      ],
      "cwd": "${workspaceFolder}/backend/laravel"
    }
  }
}
EOF
}

mcp_manifest_count() {
  printf '%s\n' "${MCP_MANIFEST[@]}" | wc -l | tr -d ' '
}

ensure_project_mcp() {
  local tmp
  tmp="$(mktemp)"
  write_project_mcp_json_to_file "$tmp"
  if [[ -f "$MCP_CONFIG" ]] && cmp -s "$tmp" "$MCP_CONFIG"; then
    rm -f "$tmp"
    echo "  OK  .cursor/mcp.json актуален"
    return 0
  fi
  mkdir -p "$(dirname "$MCP_CONFIG")"
  mv "$tmp" "$MCP_CONFIG"
  echo "  OK  записан .cursor/mcp.json ($(mcp_manifest_count) серверов)"
}

cmd_mcp_setup() {
  ensure_project_mcp
  echo ""
  cmd_mcp_check
}

cmd_mcp_list() {
  echo "hydro2.0 — манифест Cursor MCP (.cursor/mcp.json)"
  echo ""
  for entry in "${MCP_MANIFEST[@]}"; do
    local name="${entry%%|*}"
    local rest="${entry#*|}"
    local transport="${rest%%|*}"
    local desc="${rest#*|}"
    printf "  - %-24s [%s] %s\n" "$name" "$transport" "$desc"
  done
  echo ""
  echo "Опционально (не в манифесте): github (PAT), grafana (localhost:3000), playwright (E2E)"
  echo ""
  echo "После изменений: перезапусти Cursor → Settings → Tools & MCP"
  echo "Remote Espressif: Connect (GitHub/WeChat). Dev stack: make up"
}

cmd_mcp_check() {
  mcp_check_core || die "Проверка MCP не пройдена."
}

mcp_check_core() {
  local failed=0

  echo "Проверка Cursor MCP..."
  echo ""

  if [[ ! -f "$MCP_CONFIG" ]]; then
    warn "нет $MCP_CONFIG — запусти: make mcp-setup"
    return 1
  fi

  if command -v jq >/dev/null 2>&1; then
    jq empty "$MCP_CONFIG" 2>/dev/null || { warn "невалидный JSON в $MCP_CONFIG"; return 1; }
  fi

  echo "[config]"
  for entry in "${MCP_MANIFEST[@]}"; do
    local name="${entry%%|*}"
    if command -v jq >/dev/null 2>&1; then
      if jq -e --arg n "$name" '.mcpServers[$n]' "$MCP_CONFIG" >/dev/null 2>&1; then
        echo "  OK  $name"
      else
        echo "  MISS $name  (make mcp-setup)"
        failed=1
      fi
    elif grep -q "\"$name\"" "$MCP_CONFIG"; then
      echo "  OK  $name (grep)"
    else
      echo "  MISS $name"
      failed=1
    fi
  done
  echo ""

  echo "[prerequisites]"
  if command -v uvx >/dev/null 2>&1; then
    echo "  OK  uvx (mqtt MCP)"
  else
    warn "uvx не найден — mqtt MCP не запустится (установи uv: https://docs.astral.sh/uv/)"
    failed=1
  fi
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    echo "  OK  docker (postgres/redis MCP)"
  else
    warn "docker недоступен — postgres/redis MCP не запустятся"
    failed=1
  fi
  if command -v php >/dev/null 2>&1; then
    echo "  OK  php (laravel-boost)"
  else
    echo "  —   php не в PATH (laravel-boost: нужен PHP на хосте или отключи сервер)"
  fi
  if nc -z 127.0.0.1 1883 2>/dev/null; then
    echo "  OK  mqtt broker :1883"
  else
    echo "  —   mqtt :1883 не слушает (make up)"
  fi
  if nc -z 127.0.0.1 5432 2>/dev/null; then
    echo "  OK  postgres :5432"
  else
    echo "  —   postgres :5432 не слушает (make up)"
  fi
  if nc -z 127.0.0.1 6379 2>/dev/null; then
    echo "  OK  redis :6379"
  else
    echo "  —   redis :6379 не слушает (make up)"
  fi
  echo ""

  echo "[auth]"
  echo "  → espressif-docs / esp-component-registry: Cursor Settings → Tools & MCP → Connect"
  echo "  → Allowlist: espressif-docs: search_espressif_sources (при первом вызове)"
  echo ""

  if [[ "$failed" -eq 0 ]]; then
    echo "MCP конфигурация на месте."
    return 0
  fi

  return 1
}

cmd_check() {
  local failed=0

  echo "Проверка Cursor skills..."
  echo ""

  # Проектные skills
  echo "[project]"
  for rel in "${PROJECT_SKILL_DIRS[@]}"; do
    if check_skill_dir "$PROJECT_ROOT/$rel" "$rel"; then
      echo "  OK  $rel"
    else
      echo "  FAIL $rel"
      failed=1
    fi
  done
  echo ""

  # Внешние skills
  echo "[external → .agents/skills/]"
  while IFS= read -r skill; do
    [[ -n "$skill" ]] || continue
    local dir="$AGENTS_SKILLS_DIR/$skill"
    if check_skill_dir "$dir" "$skill"; then
      echo "  OK  $skill"
    else
      echo "  MISS $skill  (make skills-install)"
      failed=1
    fi
  done < <(all_external_skills)
  echo ""

  # skills-lock.json
  echo "[lockfile]"
  if [[ ! -f "$SKILLS_LOCK" ]]; then
    warn "нет skills-lock.json — запусти make skills-install"
    failed=1
  elif command -v jq >/dev/null 2>&1; then
    while IFS= read -r skill; do
      [[ -n "$skill" ]] || continue
      if jq -e --arg s "$skill" '.skills[$s]' "$SKILLS_LOCK" >/dev/null 2>&1; then
        echo "  OK  lock: $skill"
      else
        warn "skills-lock.json не содержит $skill"
        failed=1
      fi
    done < <(all_external_skills)
  else
    warn "jq не установлен — пропуск сверки skills-lock.json (make dev-tools-install)"
  fi
  echo ""

  # MCP (краткая сводка; полная проверка: make mcp-check)
  if ! mcp_check_core; then
    failed=1
  fi
  echo ""

  # Cursor marketplace plugin (опционально, только подсказка)
  if [[ -d "$HOME/.cursor/plugins/cache" ]]; then
    if find "$HOME/.cursor/plugins/cache" -path '*cursor-team-kit*' -print -quit 2>/dev/null | grep -q .; then
      echo "[marketplace] OK  cursor-team-kit plugin (user-level)"
    else
      echo "[marketplace] —   cursor-team-kit plugin не найден (опционально: /add-plugin cursor-team-kit в Cursor)"
    fi
  else
    echo "[marketplace] —   ~/.cursor/plugins/cache отсутствует (опционально)"
  fi
  echo ""

  if [[ "$failed" -eq 0 ]]; then
    echo "Все обязательные skills на месте."
    return 0
  fi

  die "Проверка skills не пройдена."
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <command>

Commands:
  install     Установить внешние skills (npx skills add → .agents/skills/)
  check       Проверить skills + MCP
  list        Показать манифест и установленные skills
  mcp-setup   Записать/обновить .cursor/mcp.json
  mcp-check   Проверить MCP конфигурацию и prerequisites
  mcp-list    Список MCP серверов проекта
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    install)   cmd_install ;;
    check)     cmd_check ;;
    list)      cmd_list ;;
    mcp-setup) cmd_mcp_setup ;;
    mcp-check) cmd_mcp_check ;;
    mcp-list)  cmd_mcp_list ;;
    ""|-h|--help) usage ;;
    *) die "Неизвестная команда: $cmd. $(usage)" ;;
  esac
}

main "$@"
