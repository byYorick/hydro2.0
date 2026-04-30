"""Smoke tests for the production automation-engine entrypoint."""

import inspect

import ae3lite.main as ae3lite_main
import main


def test_root_entrypoint_delegates_to_ae3lite_main():
    assert main.main is ae3lite_main.main


def test_ae3lite_main_is_async_entrypoint():
    assert inspect.iscoroutinefunction(ae3lite_main.main)
