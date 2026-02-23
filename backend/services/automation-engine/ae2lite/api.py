"""Canonical AE2-Lite API alias to runtime implementation."""

import sys

import ae2lite.api_runtime as _ae2_api

sys.modules[__name__] = _ae2_api
