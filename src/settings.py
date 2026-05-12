"""Global settings management using a metaclass approach."""
import json
from pathlib import Path
from typing import Any, Dict, Optional, Type


class SettingsMeta(type):
    """
    Metaclass for classes that require settings.
    Automatically registers the class with the SettingsManager.
    """
    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        if name != "Configurable":
            SettingsManager.register_class(cls)


class Configurable(metaclass=SettingsMeta):
    """Base class for configurable objects."""
    
    @classmethod
    def get_setting_keys(cls) -> Dict[str, Any]:
        """
        Return a dict of setting keys and their default values.
        Subclasses should override this.
        """
        return {}


class SettingsManager:
    """Manages global settings and persistence."""
    
    _instance = None
    _classes: Dict[str, Type[Configurable]] = {}
    _settings: Dict[str, Any] = {"globals": {}}
    _config_path = Path("data/settings.json")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    @classmethod
    def register_class(cls, target_cls: Type[Configurable]):
        """Registers a class and initializes its default settings."""
        cls._classes[target_cls.__name__] = target_cls
        
        if target_cls.__name__ not in cls._settings:
            cls._settings[target_cls.__name__] = {}
        
        defaults = target_cls.get_setting_keys()
        for key, val in defaults.items():
            if key not in cls._settings[target_cls.__name__]:
                cls._settings[target_cls.__name__][key] = val

    def get(self, class_name: str, key: str) -> Any:
        """
        Retrieves a setting value. 
        If not found in class-specific group, checks 'globals'.
        """
        # Try class-specific group
        val = self._settings.get(class_name, {}).get(key)
        if val is not None:
            return val
        
        # Fallback to globals
        return self._settings.get("globals", {}).get(key)

    def set(self, class_name: str, key: str, value: Any):
        """Sets a setting value in a group."""
        if class_name not in self._settings:
            self._settings[class_name] = {}
        self._settings[class_name][key] = value
        self._save()

    def set_global(self, key: str, value: Any):
        """Sets a global setting."""
        if "globals" not in self._settings:
            self._settings["globals"] = {}
        self._settings["globals"][key] = value
        self._save()

    def get_all_settings(self) -> Dict[str, Any]:
        """Returns all settings for UI editing."""
        return self._settings

    def _load(self):
        """Loads settings from JSON."""
        if self._config_path.exists():
            try:
                with open(self._config_path, "r") as f:
                    loaded = json.load(f)
                    # Merge loaded settings into _settings (which might already have defaults)
                    for cls_name, vals in loaded.items():
                        if cls_name not in self._settings:
                            self._settings[cls_name] = {}
                        self._settings[cls_name].update(vals)
            except Exception:
                # Fallback to defaults if file is corrupt
                pass

    def _save(self):
        """Saves settings to JSON."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._config_path, "w") as f:
                json.dump(self._settings, f, indent=4)
        except Exception:
            pass


# Global instance
settings = SettingsManager()
