# transcriber.py
import torch
import numpy as np
import gc
import os
from transformers import AutoProcessor, WhisperForConditionalGeneration
from transformers.utils import logging


import torchaudio.transforms as _TA_T

from config_manager import config
import tui

# Suppress progress bars from Hugging Face downloads
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'
os.environ['HF_HUB_VERBOSITY'] = 'error'
logging.set_verbosity_error()

# Module-level global variables
processor = None
model = None
device = None
current_model_id = None

def unload_model():
    """Unloads the model and clears the GPU cache to free memory."""
    global model, processor, current_model_id
    if model is not None:
        tui.print_info(f"Unloading model '{current_model_id}'...")
        del model
        del processor
        model = None
        processor = None
        current_model_id = None
        if device.type == 'cuda':
            torch.cuda.empty_cache()
        gc.collect()
        tui.print_success("Model unloaded and memory freed.")

def load_model(model_id: str, torch_device: torch.device):
    """Loads the Whisper model and processor into memory."""
    global processor, model, device, current_model_id

    if model is not None and model_id == current_model_id:
        tui.print_info("Model is already loaded.")
        return True

    if model is not None:
        unload_model()

    device = torch_device
    current_model_id = model_id

    tui.print_info(f"Loading model '{model_id}'...")
    tui.print_info("Downloading audio processor & model weights...")

    try:
        # --- START OF CHANGE ---
        # 1. Removed the 'rich.progress' wrapper to let transformers handle its own clean progress bar.
        # 2. Changed 'torch_dtype' to 'dtype' to fix the deprecation warning.

        processor = AutoProcessor.from_pretrained(model_id)

        model_kwargs = {}
        # Use float16 for CUDA for better performance, use the correct 'dtype' argument
        if device.type == 'cuda':
            model_kwargs = {"dtype": torch.float16, "use_safetensors": True}

        model = WhisperForConditionalGeneration.from_pretrained(model_id, **model_kwargs).to(device)
        model.eval()

        # --- END OF CHANGE ---

        tui.print_success("Model and processor loaded successfully.")
        return True
    except Exception as e:
        tui.print_error(f"Failed to load the model: {e}")
        current_model_id = None
        return False

def process_audio(audio_buffer: list, mic_sample_rate: int) -> tuple[str, int]:
    """Processes the audio buffer and returns the transcription text and token count."""
    if not audio_buffer or model is None:
        return "", 0

    raw_audio_bytes = b''.join(audio_buffer)
    if not raw_audio_bytes:
        return "", 0

    # Convert raw bytes to numpy array (float32 mono)
    audio_np = np.frombuffer(raw_audio_bytes, dtype=np.float32)

    # Apply configurable trimming at start and end (milliseconds)
    trim_start_ms = config.get('audio.trim_start_ms') or 0
    trim_end_ms = config.get('audio.trim_end_ms') or 0

    samples_to_trim_start = int(mic_sample_rate * (float(trim_start_ms) / 1000.0))
    samples_to_trim_end = int(mic_sample_rate * (float(trim_end_ms) / 1000.0))

    if samples_to_trim_start + samples_to_trim_end >= len(audio_np):
        # Nothing left after trimming
        return "", 0

    if samples_to_trim_end > 0:
        audio_np = audio_np[samples_to_trim_start: len(audio_np) - samples_to_trim_end]
    else:
        audio_np = audio_np[samples_to_trim_start:]

    # Enforce a minimum duration after trimming to avoid accidental triggers (milliseconds only)
    min_recording_ms = config.get('audio.min_recording_ms') or 0

    min_required_samples = int(mic_sample_rate * (float(min_recording_ms) / 1000.0))
    if len(audio_np) < max(min_required_samples, 1):
        # Too short after trimming; skip transcription
        duration_sec = len(audio_np) / float(mic_sample_rate)
        tui.print_info(f"Recording too short ({duration_sec:.2f}s). Skipping.")
        return "", 0

    target_sr = config.get('audio.target_sample_rate')
    if mic_sample_rate != target_sr:
        resampler = _TA_T.Resample(orig_freq=mic_sample_rate, new_freq=target_sr)
        audio_torch = resampler(torch.from_numpy(audio_np.copy()).float())
        audio_np_resampled = audio_torch.numpy()
    else:
        audio_np_resampled = audio_np

    try:
        # Prepare inputs for the model
        input_features = processor(audio_np_resampled, sampling_rate=target_sr, return_tensors="pt").input_features

        # Ensure inputs are on the correct device with the correct dtype
        dtype = torch.float16 if device.type == 'cuda' else torch.float32
        input_features = input_features.to(device, dtype=dtype)

        tui.print_info("Transcribing audio with Whisper...")

        # Get language and determine effective task (backward compatible)
        language_name = (config.get('transcription.language') or 'english')
        translate_flag = config.get('transcription.translate_to_english') or False
        task_cfg = config.get('transcription.task')
        task = 'translate' if (translate_flag or task_cfg == 'translate') else 'transcribe'

        # Try to obtain a language code from config for robustness
        available_languages = config.get('available_languages') or {}
        language_code = available_languages.get(language_name.lower())

        # Build forced decoder prompt IDs to reliably control language/task
        forced_decoder_ids = None
        if hasattr(processor, 'get_decoder_prompt_ids'):
            for lang_variant in [language_name, language_code]:
                if not lang_variant:
                    continue
                try:
                    forced_decoder_ids = processor.get_decoder_prompt_ids(language=lang_variant, task=task)
                    if forced_decoder_ids is not None:
                        break
                except Exception:
                    forced_decoder_ids = None

        # Generate transcription
        with torch.no_grad():
            if forced_decoder_ids is not None:
                generated_ids = model.generate(input_features, forced_decoder_ids=forced_decoder_ids)
            else:
                # Fallback attempts: pass language/task directly if supported
                generated_ids = None
                for lang_variant in [language_name, language_code]:
                    if generated_ids is not None or not lang_variant:
                        continue
                    try:
                        generated_ids = model.generate(input_features, language=lang_variant, task=task)
                    except Exception:
                        generated_ids = None

                if generated_ids is None:
                    # Last resort: generate without constraints
                    generated_ids = model.generate(input_features)

        # Count tokens (sequence length from generated_ids)
        token_count = generated_ids.shape[1] if generated_ids is not None and len(generated_ids.shape) >= 2 else 0

        transcription_list = processor.batch_decode(generated_ids, skip_special_tokens=True)
        transcription_text = transcription_list[0].strip() if transcription_list else ""
        return transcription_text, token_count
    except Exception as e:
        tui.print_error(f"An error occurred during Whisper inference: {e}")
        return "", 0