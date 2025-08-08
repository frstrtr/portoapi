"""
API package
Keep this lightweight to avoid side-effects when importing submodules.
The FastAPI application is defined in `src/api/v1/main.py`.
"""

# Intentionally do not import endpoints or create an app here.
# This prevents `import src.api.v1.main` from executing heavy imports at the
# package level which can fail if environment (PYTHONPATH) isn't prepared yet.

__all__ = []
