"""Compatibility alias to canonical AE2-Lite API runtime module."""

import sys

import ae2lite.api_runtime as _ae2_api

sys.modules[__name__] = _ae2_api
