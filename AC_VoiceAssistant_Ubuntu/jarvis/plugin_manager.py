"""jarvis/plugin_manager.py — Dynamic plugin engine for discovering and executing extension skills."""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class Plugin:
    """Represents an external loaded plugin."""

    def __init__(self, name: str, module: Any):
        self.name = name
        self.module = module
        self.description = getattr(module, "PLUGIN_DESCRIPTION", "")

    def can_handle(self, text: str) -> bool:
        if hasattr(self.module, "can_handle") and callable(self.module.can_handle):
            try:
                return bool(self.module.can_handle(text))
            except Exception as e:
                logger.warning("Plugin %s can_handle failed: %s", self.name, e)
        return False

    def execute(self, text: str, config: dict) -> Optional[str]:
        if hasattr(self.module, "execute") and callable(self.module.execute):
            try:
                return self.module.execute(text, config)
            except Exception as e:
                logger.warning("Plugin %s execute failed: %s", self.name, e)
                return f"Error running plugin {self.name}: {e}"
        return None


class PluginManager:
    """Discovers, loads, and dispatches to external plugins in the plugins/ directory."""

    def __init__(self, plugins_dir: str = "./plugins"):
        self.plugins_dir = Path(plugins_dir)
        self.plugins: Dict[str, Plugin] = {}
        self.load_plugins()

    def load_plugins(self) -> None:
        """Scan plugins directory and load all valid python plugins."""
        if not self.plugins_dir.exists():
            try:
                self.plugins_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning("Could not create plugins directory: %s", e)
                return

        for file_path in self.plugins_dir.glob("*.py"):
            if file_path.name.startswith("__"):
                continue
            plugin_name = file_path.stem
            try:
                spec = importlib.util.spec_from_file_location(plugin_name, file_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    self.plugins[plugin_name] = Plugin(plugin_name, mod)
                    logger.info("Loaded plugin: %s", plugin_name)
            except Exception as e:
                logger.warning("Failed to load plugin %s: %s", file_path.name, e)

    def dispatch(self, text: str, config: dict) -> Optional[str]:
        """Check if any plugin can handle the given text and execute it."""
        for plugin in self.plugins.values():
            if plugin.can_handle(text):
                logger.info("Dispatching command to plugin '%s'", plugin.name)
                return plugin.execute(text, config)
        return None

    def list_plugins(self) -> List[Dict[str, str]]:
        """List loaded plugins with name and description."""
        return [
            {"name": p.name, "description": p.description}
            for p in self.plugins.values()
        ]
