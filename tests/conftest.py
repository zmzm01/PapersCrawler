"""
pytest configuration.
Ensures src/ is on sys.path for all test imports.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
