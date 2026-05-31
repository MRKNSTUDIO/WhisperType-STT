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

def _model_id(m) -> Optional[str]:
    """Extract the repo id across huggingface_hub versions (.id vs .modelId)."""
    return getattr(m, "id", None) or getattr(m, "modelId", None)

def _list_cached_whisper_models() -> List[str]:
    """Offline fallback: list Whisper models already present in the local HF cache."""
    try:
        from huggingface_hub import scan_cache_dir
        cache = scan_cache_dir()
        return [
            r.repo_id for r in cache.repos
            if getattr(r, "repo_type", "model") == "model" and "whisper" in r.repo_id.lower()
        ]
    except Exception:
        return []

def fetch_available_whisper_models() -> List[Dict[str, str]]:
    """Fetches available Whisper models from Hugging Face, with an offline fallback.

    huggingface_hub renamed the filter kwarg across versions (older releases used
    ``task=``, v1.0+ uses ``pipeline_tag=``), so we try each form and fall back to
    listing the local cache if the API can't be reached.
    """
    ids: List[str] = []
    try:
        api = HfApi()
        models: list = []
        for kwargs in (
            {"author": "openai", "pipeline_tag": "automatic-speech-recognition"},
            {"author": "openai", "task": "automatic-speech-recognition"},
            {"author": "openai"},
        ):
            try:
                models = list(api.list_models(**kwargs))  # type: ignore[arg-type]
                break
            except TypeError:
                # Unsupported kwarg on this huggingface_hub version; try the next form.
                continue
        ids = [
            mid for m in models
            if (mid := _model_id(m)) and mid.startswith("openai/whisper-")
        ]
    except Exception:
        ids = []

    # If the network/API call failed, offer whatever is already cached locally so
    # the user is never locked out (e.g. offline first run).
    if not ids:
        ids = _list_cached_whisper_models()

    ids = sorted(set(ids), key=sort_key)
    return [{"id": mid, "name": prettify(mid)} for mid in ids]

def check_compatibility(model_id: str) -> tuple[bool, str]:
    """
    Checks if a model is compatible with the current Whisper implementation.
    Returns (is_compatible, reason).
    """
    try:
        api = HfApi()
        model_info = api.model_info(model_id)

        # Check for config.json
        files = [f.rfilename for f in (model_info.siblings or [])]
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
