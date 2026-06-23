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
  printf '%s\n' "${AWESOME_SKILLS[@]}" "${CURSOR_TEAM_SKILLS[@]}"
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

  log "Проверка после установки"
  cmd_check
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
  install   Установить внешние skills (npx skills add → .agents/skills/)
  check     Проверить манифест, SKILL.md и skills-lock.json
  list      Показать манифест и установленные skills
EOF
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    install) cmd_install ;;
    check)   cmd_check ;;
    list)    cmd_list ;;
    ""|-h|--help) usage ;;
    *) die "Неизвестная команда: $cmd. $(usage)" ;;
  esac
}

main "$@"
