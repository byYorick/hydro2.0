import asyncio
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from common.logging_setup import setup_standard_logging, install_exception_handlers
from common.trace_context import clear_trace_id, set_trace_id_from_headers

setup_standard_logging("node-sim-manager")
install_exception_handlers("node-sim-manager")
logger = logging.getLogger(__name__)

app = FastAPI(title="Node Sim Manager")


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = set_trace_id_from_headers(request.headers, fallback_generate=True)
    try:
        response = await call_next(request)
    finally:
        clear_trace_id()
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return response


@dataclass
class SessionState:
    process: subprocess.Popen
    config_path: Path
    started_at: datetime


class MqttConfig(BaseModel):
    host: str = "localhost"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    tls: bool = False
    ca_certs: Optional[str] = None
    keepalive: int = 60


class TelemetryConfig(BaseModel):
    interval_seconds: float = 5.0
    heartbeat_interval_seconds: float = 30.0
    status_interval_seconds: float = 60.0


class StartSessionRequest(BaseModel):
    session_id: str
    mqtt: Optional[MqttConfig] = None
    telemetry: Optional[TelemetryConfig] = None
    nodes: List[Dict[str, Any]]
    failure_mode: Optional[Dict[str, Any]] = None
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR)$")


class StopSessionRequest(BaseModel):
    session_id: str


class SessionResponse(BaseModel):
    status: str
    session_id: str


_sessions: Dict[str, SessionState] = {}
_sessions_lock = asyncio.Lock()


def _resolve_node_sim_root() -> Path:
    configured = os.getenv("NODE_SIM_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "tests" / "node_sim"


def _build_config(request: StartSessionRequest) -> Dict[str, Any]:
    mqtt = request.mqtt or MqttConfig()
    telemetry = request.telemetry or TelemetryConfig()

    return {
        "mqtt": mqtt.model_dump(),
        "telemetry": telemetry.model_dump(),
        "failure_mode": request.failure_mode,
        "nodes": request.nodes,
    }


def _start_process(config_path: Path, log_level_override: str) -> subprocess.Popen:
    node_sim_root = _resolve_node_sim_root()
    if not node_sim_root.exists():
        raise RuntimeError(f"node-sim root not found at {node_sim_root}")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{node_sim_root}{os.pathsep}{env.get('PYTHONPATH', '')}"

    cmd = [
        sys.executable,
        "-m",
        "node_sim.cli",
        "multi",
        "--config",
        str(config_path),
        "--log-level",
        log_level_override,
    ]

    logger.info("Starting node-sim process", extra={"cmd": " ".join(cmd)})
    return subprocess.Popen(cmd, cwd=str(node_sim_root), env=env)


@app.post("/sessions/start", response_model=SessionResponse)
async def start_session(request: StartSessionRequest) -> SessionResponse:
    if not request.nodes:
        raise HTTPException(status_code=400, detail="nodes list is required")

    async with _sessions_lock:
        existing = _sessions.get(request.session_id)
        if existing and existing.process.poll() is None:
            raise HTTPException(status_code=409, detail="session already running")

        config_data = _build_config(request)
        config_dir = Path(tempfile.mkdtemp(prefix="node-sim-"))
        config_path = config_dir / f"{request.session_id}.yaml"
        with config_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(config_data, fh)

        process = _start_process(config_path, request.log_level)
        _sessions[request.session_id] = SessionState(
            process=process,
            config_path=config_path,
            started_at=datetime.utcnow(),
        )

    return SessionResponse(status="started", session_id=request.session_id)


@app.post("/sessions/stop", response_model=SessionResponse)
async def stop_session(request: StopSessionRequest) -> SessionResponse:
    async with _sessions_lock:
        session = _sessions.get(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="session not found")

        process = session.process
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        try:
            session.config_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to remove config", extra={"path": str(session.config_path)})

        _sessions.pop(request.session_id, None)

    return SessionResponse(status="stopped", session_id=request.session_id)


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    status = "running" if session.process.poll() is None else "stopped"
    return SessionResponse(status=status, session_id=session_id)


@app.on_event("shutdown")
async def shutdown_sessions() -> None:
    async with _sessions_lock:
        for session_id, session in list(_sessions.items()):
            if session.process.poll() is None:
                session.process.terminate()
        _sessions.clear()
