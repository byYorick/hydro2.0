"""Compose и entrypoint не содержат публичных dev-паролей."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

SCAN_FILES = (
    ROOT / "backend/docker-compose.dev.yml",
    ROOT / "backend/docker-compose.dev.win.yml",
    ROOT / "backend/docker-compose.ci.yml",
    ROOT / "backend/docker-compose.prod.yml",
    ROOT / "backend/services/mqtt-bridge/mosquitto-entrypoint.sh",
    ROOT / "backend/services/mqtt-bridge/generate_passwords.sh",
    ROOT / "tests/e2e/docker-compose.e2e.yml",
    ROOT / "infra/hil/docker-compose.hil.yml",
    ROOT / "backend/laravel/bootstrap/app.php",
)

FORBIDDEN = (
    "esp32_pass",
    "logger_pass",
    "bridge_pass",
    "automation_pass",
    "python_service_pass",
    "GF_SECURITY_ADMIN_PASSWORD=admin",
    "GF_SECURITY_ADMIN_PASSWORD: admin",
    "trustProxies(at: '*')",
)


def test_compose_and_entrypoint_have_no_public_default_secrets():
    offenders: list[str] = []
    for path in SCAN_FILES:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {token}")
    assert offenders == []
