"""
Make the project root importable so ``import text_utils`` etc. work when
pytest is run from anywhere in the repo.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
