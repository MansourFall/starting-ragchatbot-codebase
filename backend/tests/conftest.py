"""
conftest.py — adds the backend/ directory to sys.path so all backend
modules are importable from the tests/ subdirectory without a package
installation step.
"""
import sys
import os

# Insert the backend directory (parent of this file) at the front of sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
