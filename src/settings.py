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
    _settings: Dict[str, Any] = {}
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
        
        # We need to initialize defaults if they don't exist in _settings
        # However, _settings might not be loaded yet if this is called during import
        # So we just ensure the class name exists in _settings
        if target_cls.__name__ not in cls._settings:
            cls._settings[target_cls.__name__] = {}
        
        # We will merge defaults during _load or when get/set is called
        # to ensure defaults are respected even if not in the JSON.
        defaults = target_cls.get_setting_keys()
        for key, val in defaults.items():
            if key not in cls._settings[target_cls.__name__]:
                cls._settings[target_cls.__name__][key] = val

    def get(self, class_name: str, key: str) -> Any:
        """Retrieves a setting value."""
        return self._settings.get(class_name, {}).get(key)

    def set(self, class_name: str, key: str, value: Any):
        """Sets a setting value and saves to disk."""
        if class_name not in self._settings:
            self._settings[class_name] = {}
        self._settings[class_name][key] = value
        self._save()

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
