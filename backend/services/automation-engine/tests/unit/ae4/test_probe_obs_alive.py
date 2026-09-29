"""probe_obs_alive читает value Prometheus как [ts, \"1\"], не как [1, …]."""

from __future__ import annotations

from ae4.application import unattended_ready as mod


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_probe_obs_alive_true_on_prometheus_vector(monkeypatch) -> None:
    body = (
        '{"status":"success","data":{"resultType":"vector","result":['
        '{"metric":{"job":"mqtt-broker"},"value":[1769000000.1,"1"]}'
        "]}}"
    )
    monkeypatch.setattr(mod, "urlopen", lambda *_a, **_k: _FakeResponse(body))
    assert mod.probe_obs_alive() is True


def test_probe_obs_alive_false_when_probe_down(monkeypatch) -> None:
    body = (
        '{"status":"success","data":{"resultType":"vector","result":['
        '{"metric":{"job":"mqtt-broker"},"value":[1769000000.1,"0"]}'
        "]}}"
    )
    monkeypatch.setattr(mod, "urlopen", lambda *_a, **_k: _FakeResponse(body))
    assert mod.probe_obs_alive() is False
