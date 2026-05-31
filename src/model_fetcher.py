# model_fetcher.py
import os
from typing import List, Dict, Optional
from huggingface_hub import HfApi, snapshot_download

PRIORITY = ["large-v3-turbo", "large-v3", "large", "medium", "small", "base", "tiny"]

def prettify(model_id: str) -> str:
    """Converts model ID to a human-readable name."""
    try:
        if "/" in model_id:
            parts = model_id.split("/", 1)
            suffix = parts[1].replace("whisper-", "").replace("-", " ")
            prefix = parts[0]
        else:
            suffix = model_id.replace("whisper-", "").replace("-", " ")
            prefix = ""

        words = suffix.split()
        words = [w.upper() if w in {"v2", "v3"} else w.capitalize() for w in words]

        friendly_name = f"Whisper {' '.join(words)}"
        if prefix and prefix != "openai":
            friendly_name += f" ({prefix})"
        return friendly_name
    except Exception:
        return model_id

def sort_key(model_id: str) -> tuple:
    """Returns a sort key for prioritizing models."""
    try:
        suffix = model_id.split("/", 1)[1].replace("whisper-", "")
        for i, key in enumerate(PRIORITY):
            if suffix.startswith(key):
                return (i, suffix)
        return (len(PRIORITY), suffix)
    except IndexError:
         return (len(PRIORITY), model_id)

def fetch_available_whisper_models() -> List[Dict[str, str]]:
    """Fetches available Whisper models from Hugging Face."""
    try:
        api = HfApi()
        # Use direct kwargs instead of ModelFilter for better compatibility
        models = api.list_models(author="openai", task="automatic-speech-recognition")
        ids = [m.modelId for m in models if m.modelId.startswith("openai/whisper-")]
        ids = sorted(set(ids), key=sort_key)
        return [{"id": mid, "name": prettify(mid)} for mid in ids]
    except Exception as e:
        return []

def check_compatibility(model_id: str) -> tuple[bool, str]:
    """
    Checks if a model is compatible with the current Whisper implementation.
    Returns (is_compatible, reason).
    """
    try:
        api = HfApi()
        model_info = api.model_info(model_id)

        # Check for config.json
        files = [f.rfilename for f in model_info.siblings]
        if "config.json" not in files:
            return False, "Missing config.json"

        # Check architecture in config
        # We'll do a lightweight fetch of config.json since model_info might not have full config
        config_path = snapshot_download(repo_id=model_id, allow_patterns=["config.json"])
        import json
        with open(os.path.join(config_path, "config.json"), 'r') as f:
            config = json.load(f)

        architectures = config.get("architectures", [])
        if not architectures:
            return False, "No architecture defined in config.json"

        if "WhisperForConditionalGeneration" not in architectures:
             return False, f"Incompatible architecture: {architectures}"

        return True, "Compatible"
    except Exception as e:
        return False, f"Error checking compatibility: {str(e)}"

def is_installed(model_id: str) -> bool:
    """Checks if a model is already downloaded locally."""
    try:
        snapshot_download(repo_id=model_id, local_files_only=True)
        return True
    except Exception:
        return False

def download_model(model_id: str) -> bool:
    """Downloads a model from Hugging Face."""
    try:
        snapshot_download(repo_id=model_id)
        return True
    except Exception:
        return False
