"""Pytest configuration: make the flat src/ modules importable.

The source modules live flat in src/ and import each other without a
package prefix (e.g. `import timings`), so src/ must be on sys.path.
"""
import os
import sys

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "src"))

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
