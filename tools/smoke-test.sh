#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
E2E_DIR="${PROJECT_ROOT}/tests/e2e"
VENV_DIR="${E2E_DIR}/venv"

log_info() {
    echo "[INFO] $1"
}

log_error() {
    echo "[ERROR] $1" >&2
}

ensure_command() {
    local name="$1"
    local hint="$2"
    if ! command -v "$name" >/dev/null 2>&1; then
        log_error "$hint"
        exit 1
    fi
}

ensure_docker_compose() {
    if command -v docker-compose >/dev/null 2>&1; then
        return 0
    fi

    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        SHIM_DIR="$(mktemp -d)"
        cat > "${SHIM_DIR}/docker-compose" <<'EOF'
#!/bin/sh
exec docker compose "$@"
EOF
        chmod +x "${SHIM_DIR}/docker-compose"
        export PATH="${SHIM_DIR}:${PATH}"
        trap 'rm -rf "${SHIM_DIR}"' EXIT
        return 0
    fi

    log_error "docker-compose not found (install Docker Compose or enable docker compose plugin)."
    exit 1
}

load_env_file() {
    local env_file="$1"
    if [ -f "$env_file" ]; then
        # shellcheck disable=SC2046
        export $(grep -v '^#' "$env_file" | xargs)
        log_info "Loaded env from ${env_file}"
    fi
}

main() {
    ensure_command "python3" "python3 not found (install Python 3)."
    ensure_docker_compose

    if [ ! -f "${E2E_DIR}/requirements.txt" ]; then
        log_error "Missing ${E2E_DIR}/requirements.txt"
        exit 1
    fi

    if [ -f "${E2E_DIR}/.env.e2e" ]; then
        load_env_file "${E2E_DIR}/.env.e2e"
    elif [ -f "${E2E_DIR}/.env.e2e.example" ]; then
        load_env_file "${E2E_DIR}/.env.e2e.example"
    fi

    if [ ! -d "$VENV_DIR" ]; then
        log_info "Creating venv at ${VENV_DIR}"
        python3 -m venv "$VENV_DIR"
    fi

    log_info "Installing E2E dependencies"
    "${VENV_DIR}/bin/pip" install -q -r "${E2E_DIR}/requirements.txt"

    local scenarios=(
        "core/E01_bootstrap.yaml"
        "commands/E10_command_happy.yaml"
    )

    log_info "Running smoke scenarios: ${scenarios[*]}"
    cd "$E2E_DIR"
    local report_dir="${E2E_REPORT_DIR:-${E2E_DIR}/reports/smoke}"
    mkdir -p "$report_dir"
    PYTHONPATH="$E2E_DIR" "${VENV_DIR}/bin/python3" -m runner.suite --fail-fast --output "$report_dir" "${scenarios[@]}"
}

main "$@"
