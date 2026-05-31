# main.py
import time
try:
    import keyboard as _keyboard
    KEYBOARD_AVAILABLE = True
except Exception:
    _keyboard = None
    KEYBOARD_AVAILABLE = False
import threading
import warnings
import torch
from rich.markup import escape

from config_manager import config
import tui
import hardware_manager
import transcriber
from audio_handler import AudioRecorder
from model_fetcher import fetch_available_whisper_models, is_installed, download_model, prettify
_pyperclip_error = None
try:
    import pyperclip as _pyperclip
    CLIPBOARD_AVAILABLE = True
except Exception as e:
    _pyperclip = None
    CLIPBOARD_AVAILABLE = False
    _pyperclip_error = str(e)

is_recording = False
app_running = True

def type_text(text: str):
    if not text:
        return
    if not KEYBOARD_AVAILABLE:
        tui.print_info("Keyboard automation not available on this platform. Showing text only.")
        return
    try:
        time.sleep(0.05)
        _keyboard.write(text, delay=0.001)
        tui.print_success("Text entered into the active field.")
    except Exception as e:
        tui.print_error(f"Failed to type text automatically: {e}")

def paste_text(text: str, restore_clipboard: bool = False):
    if not text:
        return
    if not KEYBOARD_AVAILABLE:
        tui.print_info("Keyboard automation not available on this platform. Paste mode disabled.")
        return
    if not CLIPBOARD_AVAILABLE:
        tui.print_error("Clipboard not available. Falling back to direct typing.")
        type_text(text)
        return

    prev_clipboard = None
    try:
        if restore_clipboard:
            try:
                prev_clipboard = _pyperclip.paste()
            except Exception:
                prev_clipboard = None

        _pyperclip.copy(text)
        time.sleep(0.05)
        _keyboard.press_and_release('ctrl+v')
        tui.print_success("Text pasted into the active field.")
    except Exception as e:
        tui.print_error(f"Failed to paste text: {e}")
        if prev_clipboard:
            try:
                _pyperclip.copy(prev_clipboard)
            except Exception:
                pass
    finally:
        if restore_clipboard and prev_clipboard is not None:
            try:
                _pyperclip.copy(prev_clipboard)
            except Exception:
                pass

def transcribe_and_type(audio_buffer, sample_rate):
    transcription, token_count = transcriber.process_audio(audio_buffer, sample_rate)
    if transcription:
        tui.display_transcription(transcription, token_count)

        # Display translation status if translation is enabled (happens during transcription)
        translate_flag = config.get('transcription.translate_to_english') or False
        task_cfg = config.get('transcription.task')
        effective_translate = bool(translate_flag or (task_cfg == 'translate'))
        if effective_translate:
            current_language = config.get('transcription.language')
            if isinstance(current_language, str):
                tui.print_success(f"Translated {current_language.capitalize()} input to English")
            else:
                tui.print_success("Translated input to English")

        # Read config flags with defaults
        copy_to_clipboard = config.get('transcription.copy_to_clipboard')
        if copy_to_clipboard is None:
            copy_to_clipboard = True
        type_into_active_field = config.get('transcription.type_into_active_field')
        if type_into_active_field is None:
            type_into_active_field = True
        type_mode = config.get('transcription.type_mode')
        if type_mode is None:
            type_mode = 'direct'

        # Paste mode requires clipboard to be enabled
        if type_mode == 'paste':
            copy_to_clipboard = True

        text_with_space = transcription + " "

        # Handle auto-typing/pasting (requires keyboard module)
        if type_into_active_field:
            if KEYBOARD_AVAILABLE:
                if type_mode == 'paste':
                    # Paste mode: use clipboard + Ctrl+V
                    # In paste mode, clipboard is always used, so restore_clipboard=False
                    paste_text(text_with_space, restore_clipboard=False)
                else:
                    # Direct mode: type characters directly
                    type_text(text_with_space)
            else:
                tui.print_info("Keyboard automation not available on this platform. Auto-type disabled.")

        # Handle clipboard copying (only if not already handled by paste mode)
        # If paste mode is used, clipboard is already handled in paste_text()
        if copy_to_clipboard and not (type_into_active_field and type_mode == 'paste'):
            if CLIPBOARD_AVAILABLE:
                try:
                    _pyperclip.copy(text_with_space)
                    tui.print_success("Copied transcription to clipboard.")
                except Exception as e:
                    tui.print_error(f"Failed to copy to clipboard: {e}")
            else:
                error_msg = _pyperclip_error if _pyperclip_error else 'unknown error'
                tui.print_error(
                    f"Clipboard support not available (pyperclip import failed: {error_msg}). "
                    "Make sure you ran 'install.bat' or installed dependencies in the active virtualenv."
                )

        # If both are disabled, only display was shown
        if not copy_to_clipboard and not type_into_active_field:
            tui.print_info("Both clipboard and auto-type are disabled. Transcription displayed in terminal only.")

def main_loop(device: torch.device):
    global is_recording, app_running
    recorder = AudioRecorder()
    toggle_key_was_pressed = False

    while app_running:
        time.sleep(0.05)

        try:
            if KEYBOARD_AVAILABLE and _keyboard.is_pressed((config.get('hotkeys.settings_key_combination') or '').lower()):
                tui.print_info("Settings hotkey pressed. Opening options...")
                new_model_id = tui.show_settings_menu()
                if new_model_id:
                    # Persist selection so the ready banner shows the correct model name
                    config.set('transcription.model_id', new_model_id)
                    transcriber.load_model(new_model_id, device)
                    tui.print_ready_message()
                time.sleep(0.5)
                continue

            exit_key = (config.get('hotkeys.exit_key_combination') or '').lower()
            if KEYBOARD_AVAILABLE and exit_key and _keyboard.is_pressed(exit_key):
                if exit_key == 'ctrl+c':
                    try:
                        import ctypes
                        kernel32 = ctypes.windll.kernel32
                        user32 = ctypes.windll.user32
                        hwnd = kernel32.GetConsoleWindow()
                        if hwnd:
                            foreground = user32.GetForegroundWindow()
                            if foreground != hwnd:
                                continue
                    except Exception:
                        pass
                tui.print_info("Quit key combination pressed. Shutting down...")
                app_running = False
                break
        except Exception:
            pass

        mode = config.get('hotkeys.hotkey_mode')
        if KEYBOARD_AVAILABLE and mode == 'toggle':
            toggle_key = (config.get('hotkeys.toggle_key') or '').lower()
            if KEYBOARD_AVAILABLE and _keyboard.is_pressed(toggle_key):
                if not toggle_key_was_pressed:
                    toggle_key_was_pressed = True
                    is_recording = not is_recording
                    if is_recording:
                        recorder.start_recording()
                    else:
                        audio_buffer = recorder.stop_recording()
                        if audio_buffer:
                            threading.Thread(target=transcribe_and_type, args=(audio_buffer, recorder.mic_sample_rate), daemon=True).start()
            else:
                toggle_key_was_pressed = False

        elif KEYBOARD_AVAILABLE and mode != 'toggle': # pushtotalk mode
            ptt_key = (config.get('hotkeys.pushtotalk_key') or '').lower()
            if KEYBOARD_AVAILABLE and _keyboard.is_pressed(ptt_key):
                if not is_recording:
                    is_recording = True
                    recorder.start_recording()
            elif is_recording:
                is_recording = False
                audio_buffer = recorder.stop_recording()
                if audio_buffer:
                    threading.Thread(target=transcribe_and_type, args=(audio_buffer, recorder.mic_sample_rate), daemon=True).start()
        # If hotkeys are unavailable, the application will only work with hotkey-enabled systems
        # Manual mode removed as it relied on Unix-specific terminal APIs

    if is_recording:
        recorder.stop_recording()
    tui.print_info("Application has been shut down.")

def initial_model_wizard():
    """First-run wizard: optionally download multiple models, then select active model."""
    tui.console.print("\n[bold cyan]Initial Setup Wizard[/bold cyan]")
    tui.console.print("Let's set up your Whisper models.\n")

    tui.print_info("Fetching available Whisper models from Hugging Face...")
    models = fetch_available_whisper_models()
    if not models:
        tui.print_error("Could not fetch models from Hugging Face. Check your internet connection.")
        return None

    tui.console.print(f"[green]Found {len(models)} available models.[/green]\n")

    import questionary

    download_choices = []
    for model in models:
        installed_marker = " [Installed]" if is_installed(model['id']) else ""
        download_choices.append(questionary.Choice(
            title=f"{model['name']}{installed_marker}",
            value=model['id']
        ))

    selected_models = questionary.checkbox(
        "Select models to download (optional - you can skip this and download later):",
        choices=download_choices
    ).ask()

    if selected_models:
        tui.console.print(f"\n[bold]Downloading {len(selected_models)} model(s)...[/bold]\n")
        for model_id in selected_models:
            if is_installed(model_id):
                tui.print_info(f"Skipping {prettify(model_id)} (already installed)")
                continue

            tui.print_info(f"Downloading {prettify(model_id)}...")
            if download_model(model_id):
                tui.print_success(f"Downloaded {prettify(model_id)}")
            else:
                tui.print_error(f"Failed to download {prettify(model_id)}")

    tui.console.print("\n[bold]Now select your active model:[/bold]\n")
    selected_model_id = tui.select_active_model()

    return selected_model_id

def main():
    tui.print_welcome()

    # Check if model_id and language are already configured
    selected_model_id = config.get('transcription.model_id')
    selected_language = config.get('transcription.language')

    # Only prompt for model selection if not already configured
    if not selected_model_id:
        selected_model_id = initial_model_wizard()
        if not selected_model_id:
            tui.print_error("No model was selected. Exiting program.")
            return
        config.set('transcription.model_id', selected_model_id)
    else:
        tui.print_info(f"Using configured model: {prettify(selected_model_id)}")

    # Only prompt for language selection if not already configured
    if not selected_language:
        selected_language = tui.select_language()
        if not selected_language:
            tui.print_error("No language was selected. Exiting program.")
            return
        config.set('transcription.language', selected_language)
    else:
        tui.print_info(f"Using configured language: {selected_language.capitalize()}")

    device = hardware_manager.get_device()
    if not transcriber.load_model(selected_model_id, device):
        tui.print_error("Failed to load the model. Exiting program.")
        return

    tui.print_success(f"{config.get('app.name')} is ready!")
    tui.print_ready_message()
    main_loop(device)

if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=UserWarning, message="FP16 is not supported on CPU")
    warnings.filterwarnings("ignore", category=UserWarning, module='pyaudio')

    try:
        main()
    except Exception as e:
        tui.print_error(f"An unexpected critical error occurred: {escape(str(e))}")