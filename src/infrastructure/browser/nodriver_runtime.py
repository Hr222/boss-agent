"""Shared nodriver bootstrap helpers."""

import asyncio
import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Awaitable

_NODRIVER_LOGGED = False


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _import_nodriver():
    """Load nodriver from installed packages, project venv, or vendored source."""
    global _NODRIVER_LOGGED
    project_root = Path(__file__).resolve().parents[3]
    repo_root = project_root / "nodriver"
    package_root = repo_root / "nodriver"
    project_venv_site_packages = project_root / ".venv" / "Lib" / "site-packages"

    try:
        uc = importlib.import_module("nodriver")
        if hasattr(uc, "start"):
            if _env_bool("BOSS_DEBUG", False):
                if not _NODRIVER_LOGGED:
                    print(f"[nodriver] using installed: {getattr(uc, '__file__', uc)}")
                    _NODRIVER_LOGGED = True
            return uc
    except Exception:
        pass

    if project_venv_site_packages.exists():
        if "nodriver" in sys.modules:
            del sys.modules["nodriver"]
        sys.path.insert(0, str(project_venv_site_packages))
        try:
            uc = importlib.import_module("nodriver")
            if hasattr(uc, "start"):
                if _env_bool("BOSS_DEBUG", False):
                    if not _NODRIVER_LOGGED:
                        print(f"[nodriver] using project venv: {getattr(uc, '__file__', uc)}")
                        _NODRIVER_LOGGED = True
                return uc
        except Exception:
            pass

    if repo_root.exists() and package_root.exists():
        sys.path.insert(0, str(repo_root))
        if "nodriver" in sys.modules:
            del sys.modules["nodriver"]
        try:
            uc = importlib.import_module("nodriver")
        except Exception:
            uc = None

        if uc is None or not hasattr(uc, "start"):
            spec = importlib.util.spec_from_file_location(
                "nodriver",
                str(package_root / "__init__.py"),
                submodule_search_locations=[str(package_root)],
            )
            if spec is None or spec.loader is None:
                raise ModuleNotFoundError("Failed to load local nodriver package.")
            module = importlib.util.module_from_spec(spec)
            sys.modules["nodriver"] = module
            spec.loader.exec_module(module)
            uc = module

        if _env_bool("BOSS_DEBUG", False):
            if not _NODRIVER_LOGGED:
                print(f"[nodriver] using vendored: {getattr(uc, '__file__', uc)}")
                _NODRIVER_LOGGED = True
        return uc

    raise ModuleNotFoundError(
        "nodriver is not installed and no local vendored package was found. "
        "Install it with `pip install -r requirements.txt`."
    )


def run_async_entrypoint(entrypoint: Awaitable[None]) -> None:
    """Run an async entrypoint with nodriver-compatible loop handling."""
    uc = _import_nodriver()
    loop_fn = getattr(uc, "loop", None)
    if callable(loop_fn):
        loop_fn().run_until_complete(entrypoint)
        return

    try:
        from nodriver.core.util import loop as nd_loop  # type: ignore

        nd_loop().run_until_complete(entrypoint)
    except Exception:
        asyncio.run(entrypoint)
