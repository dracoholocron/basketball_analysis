"""Shared pytest fixtures for basketball analytics test suite."""
import sys
import os
import pytest

# Make the engine package importable without install
ENGINE_PATH = os.path.join(os.path.dirname(__file__), "..", "basketball_analysis", "basketball_analysis")
if ENGINE_PATH not in sys.path:
    sys.path.insert(0, ENGINE_PATH)

# Make the api package importable
API_PATH = os.path.join(os.path.dirname(__file__), "..", "api")
if API_PATH not in sys.path:
    sys.path.insert(0, API_PATH)
