# config_manager.py
import json
import os
from version import __version__

CONFIG_FILE_NAME = "user_config.json"

class ConfigManager:
    """
    Manages all application settings, loading defaults and user customizations
    from a JSON file.
    """

    def __init__(self):
        # Define the default configuration here
        self._defaults = {
            "app": {
                "name": "WhisperType",
                "version": __version__,
                "first_run_completed": False
            },
            "audio": {
                "target_sample_rate": 16000, "pyaudio_format": "paFloat32", "channels": 1,
                "chunk_size": 1024, "min_recording_ms": 500, "trim_start_ms": 150, "trim_end_ms": 150
            },
            "hotkeys": {
                # A single record key is used for BOTH modes. "hotkey_mode"
                # decides whether pressing it toggles recording or records only
                # while held (push-to-talk). F9 is on virtually every keyboard,
                # does not insert text, and does not clash with the terminal.
                "hotkey_mode": "toggle",
                "record_key": "f9",
                "exit_key_combination": "ctrl+q",
                "settings_key_combination": "f1"
            },
            "transcription": {
                "language": "english", "task": "transcribe", "translate_to_english": False,
                "copy_to_clipboard": True, "type_into_active_field": True, "type_mode": "direct"
            },
            "available_languages": {
                "english": "en", "chinese": "zh", "german": "de", "spanish": "es", "russian": "ru",
                "korean": "ko", "french": "fr", "japanese": "ja", "portuguese": "pt", "turkish": "tr",
                "polish": "pl", "catalan": "ca", "dutch": "nl", "arabic": "ar", "swedish": "sv",
                "italian": "it", "indonesian": "id", "hindi": "hi", "finnish": "fi", "vietnamese": "vi",
                "hebrew": "he", "ukrainian": "uk", "greek": "el", "malay": "ms", "czech": "cs",
                "romanian": "ro", "danish": "da", "hungarian": "hu", "tamil": "ta", "norwegian": "no",
                "thai": "th", "urdu": "ur", "croatian": "hr", "bulgarian": "bg", "lithuanian": "lt",
                "latin": "la", "maori": "mi", "malayalam": "ml", "welsh": "cy", "slovak": "sk",
                "telugu": "te", "persian": "fa", "latvian": "lv", "bengali": "bn", "serbian": "sr",
                "azerbaijani": "az", "slovenian": "sl", "kannada": "kn", "estonian": "et", "macedonian": "mk",
                "breton": "br", "basque": "eu", "icelandic": "is", "armenian": "hy", "nepali": "ne",
                "mongolian": "mn", "bosnian": "bs", "kazakh": "kk", "albanian": "sq", "swahili": "sw",
                "galician": "gl", "marathi": "mr", "punjabi": "pa", "sinhala": "si", "khmer": "km",
                "shona": "sn", "yoruba": "yo", "somali": "so", "afrikaans": "af", "occitan": "oc",
                "georgian": "ka", "belarusian": "be", "tajik": "tg", "sindhi": "sd", "gujarati": "gu",
                "amharic": "am", "yiddish": "yi", "lao": "lo", "uzbek": "uz", "faroese": "fo",
                "haitian creole": "ht", "pashto": "ps", "turkmen": "tk", "nynorsk": "nn", "maltese": "mt",
                "sanskrit": "sa", "luxembourgish": "lb", "myanmar": "my", "tibetan": "bo", "tagalog": "tl",
                "malagasy": "mg", "assamese": "as", "tatar": "tt", "hawaiian": "haw", "lingala": "ln",
                "hausa": "ha", "bashkir": "ba", "javanese": "jw", "sundanese": "su", "cantonese": "yue"
            }
        }
        self.config = {}
        self.load_config()

    def _deep_merge(self, defaults: dict, user_settings: dict) -> dict:
        merged = defaults.copy()
        for key, value in user_settings.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def load_config(self):
        defaults_copy = self._defaults.copy()
        old_version = None
        migrated = False
        if os.path.exists(CONFIG_FILE_NAME):
            try:
                with open(CONFIG_FILE_NAME, 'r') as f:
                    user_config = json.load(f)
                # Store old version before removing it
                if "app" in user_config and "version" in user_config.get("app", {}):
                    old_version = user_config["app"]["version"]
                    user_config["app"].pop("version", None)
                # Migrate the RAW user config before merging, so defaults don't
                # mask whether the user had explicitly chosen a record key.
                migrated = self._migrate_hotkeys(user_config.get("hotkeys"))
                self.config = self._deep_merge(defaults_copy, user_config)
            except Exception as e:
                print(f"[ERROR] Could not load {CONFIG_FILE_NAME}: {e}. Using default settings.")
                self.config = defaults_copy
        else:
            self.config = defaults_copy
            self.save_config()
        # Always ensure version is from version.py
        if "app" not in self.config:
            self.config["app"] = {}
        self.config["app"]["version"] = __version__

        # Update config file if version changed (or was missing) or migrated.
        if old_version != __version__ or migrated:
            self.save_config()

    def _migrate_hotkeys(self, hk) -> bool:
        """Upgrade old configs that used separate toggle_key/pushtotalk_key to a
        single record_key. Operates on the raw user hotkeys dict (pre-merge).
        Returns True if anything was changed."""
        if not isinstance(hk, dict):
            return False
        changed = False
        # Ensure a record_key exists. Preserve a genuinely custom legacy key, but
        # retire the old defaults (scroll lock / right ctrl) in favour of the new
        # universal default, since those are exactly what we're moving away from.
        if not hk.get("record_key"):
            retired = {"scroll lock", "right ctrl"}
            legacy = (hk.get("toggle_key") or hk.get("pushtotalk_key") or "").strip()
            if legacy and legacy.lower() not in retired:
                hk["record_key"] = legacy
            else:
                hk["record_key"] = self._defaults["hotkeys"]["record_key"]
            changed = True
        # Drop obsolete keys so the config stays clean.
        for old in ("toggle_key", "pushtotalk_key"):
            if old in hk:
                del hk[old]
                changed = True
        return changed

    def save_config(self):
        try:
            # Ensure version is always current before saving
            if "app" not in self.config:
                self.config["app"] = {}
            self.config["app"]["version"] = __version__
            with open(CONFIG_FILE_NAME, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"[ERROR] Could not save settings to {CONFIG_FILE_NAME}: {e}")

    def get(self, key_path: str):
        keys = key_path.split('.')
        value = self.config
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            print(f"[WARNING] Config key not found: {key_path}")
            return None

    def set(self, key_path: str, value):
        if key_path == "app.version":
            print(f"[WARNING] Version cannot be changed. Current version: {__version__}")
            return
        keys = key_path.split('.')
        d = self.config
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value
        self.save_config()

config = ConfigManager()