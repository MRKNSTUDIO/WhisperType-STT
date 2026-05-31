# tui.py
import questionary
import os
try:
    import keyboard as _keyboard
    KEYBOARD_AVAILABLE = True
except Exception:
    _keyboard = None
    KEYBOARD_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except Exception:
    psutil = None
    PSUTIL_AVAILABLE = False

from rich.console import Console
from rich.panel import Panel
from rich.markup import escape
from typing import Optional
from config_manager import config
from model_fetcher import fetch_available_whisper_models, is_installed, download_model, prettify, check_compatibility

console = Console()

def print_welcome():
    console.print(Panel(
        f"[bold magenta]{config.get('app.name')}[/bold magenta] - Your Speech-to-Text Assistant",
        title="[bold green]Welcome![/bold green]",
        subtitle=f"[cyan]Version {config.get('app.version')}[/cyan]"
    ))

def print_error(message: str):
    console.print(f"[bold red]ERROR:[/bold red] {message}")

def print_info(message: str):
    console.print(f"[bold blue]INFO:[/bold blue] {message}")

def print_success(message: str):
    console.print(f"[bold green]✓[/bold green] {message}")

def select_active_model() -> Optional[str]:
    """Selects the active model from available Whisper models."""
    console.print("\n[bold]Model Selection[/bold]")
    print_info("Fetching available Whisper models from Hugging Face...")

    models = fetch_available_whisper_models()
    if not models:
        print_error("Could not fetch models from Hugging Face. Check your internet connection.")
        return None

    model_choices = []
    for model in models:
        installed_marker = " [Installed]" if is_installed(model['id']) else " [Not Installed]"
        model_choices.append(questionary.Choice(
            title=f"{model['name']}{installed_marker}",
            value=model['id']
        ))

    try:
        model_id = questionary.select(
            "Which Whisper model would you like to use?",
            choices=model_choices,
            use_indicator=True
        ).ask()

        if model_id:
            if not is_installed(model_id):
                print_info(f"Model '{prettify(model_id)}' is not installed. Downloading...")
                if download_model(model_id):
                    print_success(f"Downloaded {prettify(model_id)}")
                else:
                    print_error(f"Failed to download {prettify(model_id)}")
                    return None
            print_success(f"Model selected: {prettify(model_id)}")
        return model_id
    except (KeyboardInterrupt, TypeError):
        return None

def select_language() -> Optional[str]:
    console.print("\n[bold]Language Selection[/bold]")
    available_languages = config.get('available_languages')
    if not available_languages:
        print_error("No languages defined in the configuration.")
        return None

    languages = sorted(available_languages.keys())
    cols = 4
    col_gap = 4  # horizontal spaces between columns

    # Default selection = current config language if present
    current_language = config.get('transcription.language')
    selected_index = languages.index(current_language) if current_language in languages else 0

    # Rich Live-based grid navigation (no duplicated prints)
    try:
        import msvcrt
        from rich.table import Table
        from rich.live import Live
        from rich.console import Group
        from rich.text import Text

        def build_renderable(selected: int):
            table = Table.grid(padding=(0, col_gap), pad_edge=False, expand=False)
            for _ in range(cols):
                table.add_column(justify="left", no_wrap=True)

            # Build rows
            for row_start in range(0, len(languages), cols):
                cells = []
                for col in range(cols):
                    idx = row_start + col
                    if idx < len(languages):
                        lang = languages[idx]
                        if idx == selected:
                            cells.append(Text(f"● {lang}", style="black on white"))
                        else:
                            cells.append(Text(f"○ {lang}"))
                    else:
                        cells.append(Text(""))
                table.add_row(*cells)

            selected_text = Text(f"Selected: {languages[selected]}", style="bold cyan")
            instructions = Text("Use arrow keys to navigate • Enter to select • Ctrl+C to cancel", style="dim")
            return Group(table, Text(""), selected_text, instructions)

        with Live(build_renderable(selected_index), console=console, refresh_per_second=60, transient=False) as live:
            while True:
                key = msvcrt.getch()

                if key in (b"\x00", b"\xe0"):
                    key = msvcrt.getch()
                    if key == b"H":  # Up
                        if selected_index - cols >= 0:
                            selected_index -= cols
                    elif key == b"P":  # Down
                        if selected_index + cols < len(languages):
                            selected_index += cols
                    elif key == b"K":  # Left
                        if (selected_index % cols) > 0:
                            selected_index -= 1
                    elif key == b"M":  # Right
                        if (selected_index % cols) < (cols - 1) and (selected_index + 1) < len(languages):
                            selected_index += 1
                    live.update(build_renderable(selected_index))

                elif key == b"\r":  # Enter
                    chosen = languages[selected_index]
                    print_success(f"Language set to: {chosen.capitalize()}")
                    return chosen

                elif key == b"\x03":  # Ctrl+C
                    print_info("Language selection cancelled.")
                    return None

    except Exception:
        # Fallback to simple list selection
        try:
            language = questionary.select(
                "What language will you be speaking in?",
                choices=languages,
                use_indicator=True,
                default=current_language
            ).ask()
            if language:
                print_success(f"Language set to: {language.capitalize()}")
            return language
        except (KeyboardInterrupt, TypeError):
            return None

def format_bytes(bytes_size: float) -> str:
    """Formats bytes to human-readable format."""
    size = float(bytes_size)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def get_ram_usage() -> Optional[str]:
    """Gets current RAM usage."""
    try:
        if PSUTIL_AVAILABLE:
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            return format_bytes(mem_info.rss)
        else:
            return None
    except Exception:
        return None

def get_vram_usage() -> Optional[tuple[str, str]]:
    """Gets current VRAM usage. Returns (allocated, total) or None."""
    try:
        import torch
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated()
            total = torch.cuda.get_device_properties(0).total_memory
            return (format_bytes(allocated), format_bytes(total))
        return None
    except Exception:
        return None

def get_model_size_from_loaded_model() -> Optional[str]:
    """Gets the size of the loaded model parameters in memory (most accurate)."""
    try:
        import transcriber
        import torch
        
        if transcriber.model is None:
            return None
        
        # Calculate total size of all model parameters
        total_params = 0
        for param in transcriber.model.parameters():
            total_params += param.numel() * param.element_size()
        
        # Also include buffers (like batch norm running stats)
        for buffer in transcriber.model.buffers():
            total_params += buffer.numel() * buffer.element_size()
        
        return format_bytes(total_params) if total_params > 0 else None
    except Exception:
        return None

def get_model_size(model_id: Optional[str]) -> Optional[str]:
    """Gets the size of the model weights on disk (only weight files, not config/tokenizer)."""
    if not model_id:
        return None
    
    # First, try to get size from loaded model (most accurate)
    loaded_size = get_model_size_from_loaded_model()
    if loaded_size:
        return loaded_size
    
    # Fallback: calculate from disk (only weight files)
    try:
        from huggingface_hub import snapshot_download

        cache_dir = snapshot_download(repo_id=model_id, local_files_only=True)
        if not cache_dir:
            return None

        # Only count weight files (.bin, .safetensors), not config/tokenizer files
        weight_extensions = {'.bin', '.safetensors'}
        total_size = 0
        for root, dirs, files in os.walk(cache_dir):
            for file in files:
                # Only count weight files
                if any(file.endswith(ext) for ext in weight_extensions):
                    file_path = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(file_path)
                    except (OSError, FileNotFoundError):
                        pass

        return format_bytes(total_size) if total_size > 0 else None
    except Exception:
        return None

def print_ready_message():
    console.print("")
    console.print("="*60)

    # Display current model and language information
    current_model_id = config.get('transcription.model_id')
    current_language = config.get('transcription.language')

    # Find the human-readable model name
    model_name = prettify(current_model_id) if current_model_id else "Not Set"

    # Determine effective translation mode (backward compatible with legacy 'task')
    translate_flag = config.get('transcription.translate_to_english') or False
    task_cfg = config.get('transcription.task')
    effective_translate = bool(translate_flag or (task_cfg == 'translate'))

    console.print(f"[bold magenta]Active Model:[/bold magenta]   {model_name}")

    if effective_translate:
        console.print(f"[bold magenta]Input Language:[/bold magenta] {current_language.capitalize()} (Translate to English: On)")
    else:
        console.print(f"[bold magenta]Input Language:[/bold magenta] {current_language.capitalize()}")

    # Display model size
    model_size = get_model_size(current_model_id)
    if model_size:
        console.print(f"[bold magenta]Model Size:[/bold magenta]     {model_size}")

    # Display RAM usage
    ram_usage = get_ram_usage()
    if ram_usage:
        console.print(f"[bold magenta]RAM Usage:[/bold magenta]      {ram_usage}")

    # Display VRAM usage if GPU is available
    vram_info = get_vram_usage()
    if vram_info:
        allocated, total = vram_info
        console.print(f"[bold magenta]VRAM Usage:[/bold magenta]     {allocated} / {total}")

    if isinstance(current_model_id, str) and 'openai/whisper-large-v3-turbo' in current_model_id and effective_translate:
        console.print("[yellow]Note: English translation may be inconsistent with Turbo. Consider using 'Whisper Large v3' for best results.[/yellow]")
    console.print("")

    if KEYBOARD_AVAILABLE:
        mode = config.get('hotkeys.hotkey_mode')
        if mode == 'toggle':
            record_key = config.get('hotkeys.toggle_key')
            console.print(f"[bold magenta]Record Mode:[/bold magenta]   Press '{record_key}' to start/stop recording.")
        else: # pushtotalk
            record_key = config.get('hotkeys.pushtotalk_key')
            console.print(f"[bold magenta]Push-to-Talk:[/bold magenta]  HOLD '{record_key}' to record.")

        console.print(f"[bold magenta]Settings:[/bold magenta]      Press '{config.get('hotkeys.settings_key_combination')}' to open options.")
        console.print(f"[bold magenta]Quit:[/bold magenta]          Press '{config.get('hotkeys.exit_key_combination')}' to quit.")
    else:
        console.print("[yellow]Hotkeys unavailable. Ensure 'keyboard' package is installed and working.[/yellow]")
    console.print("="*60 + "\n")

def display_transcription(text_to_display: str, token_count: int = 0):
    console.print(f"[yellow]Transcription:[/yellow] [italic grey50]{text_to_display}[/italic grey50]")
    if token_count > 0:
        console.print(f"[dim]Tokens used: {token_count}[/dim]")

def prompt_for_hotkey(prompt_message: str) -> Optional[str]:
    console.print(f"\n[bold yellow]-- {prompt_message} --[/bold]")
    console.print("[italic grey50](Press 'Ctrl+C' to cancel)[/italic]")
    try:
        if not KEYBOARD_AVAILABLE:
            print_info("Keyboard module not available on this platform.")
            return None
        else:
            hotkey = _keyboard.read_hotkey(suppress=False)
        if hotkey == 'ctrl+c':
            print_info("Hotkey selection cancelled.")
            return None
        print_success(f"New key set to: '{hotkey}'")
        return hotkey
    except Exception as e:
        print_error(f"Could not read hotkey: {escape(str(e))}")
        return None

def show_hotkey_settings_menu():
    last_choice = None
    while True:
        try:
            current_mode = config.get('hotkeys.hotkey_mode')
            toggle_key = config.get('hotkeys.toggle_key')
            ptt_key = config.get('hotkeys.pushtotalk_key')

            choices = [
                questionary.Choice(f"Change Mode (Current: {current_mode})", value="change_mode"),
                questionary.Choice(f"Set Toggle Key (Current: '{toggle_key}')", value="set_toggle_key"),
                questionary.Choice(f"Set Push-to-Talk Key (Current: '{ptt_key}')", value="set_ptt_key"),
                questionary.Separator(),
                questionary.Choice("Back to main menu", value="back")
            ]

            choice = questionary.select("Hotkey Settings", choices=choices, use_indicator=True, default=last_choice).ask()

            if choice == "back" or choice is None:
                break

            last_choice = choice

            if choice == "change_mode":
                new_mode = questionary.select(
                    "Select your preferred recording mode:",
                    choices=[
                        "Toggle (Press a key to start, press it again to stop)",
                        "Push-to-Talk (Hold a key to record)"
                    ],
                    default="Toggle" if current_mode == 'toggle' else "Push-to-Talk"
                ).ask()
                if new_mode:
                    config.set('hotkeys.hotkey_mode', 'toggle' if 'Toggle' in new_mode else 'pushtotalk')
                    print_success(f"Hotkey mode set to '{config.get('hotkeys.hotkey_mode')}'.")

            elif choice == "set_toggle_key":
                new_key = prompt_for_hotkey("Press the key for Toggle Mode...")
                if new_key:
                    config.set('hotkeys.toggle_key', new_key)

            elif choice == "set_ptt_key":
                new_key = prompt_for_hotkey("Press the key for Push-to-Talk Mode...")
                if new_key:
                    config.set('hotkeys.pushtotalk_key', new_key)
        except (KeyboardInterrupt, TypeError):
            break

def _prompt_int_in_range(message: str, default_value: int, min_value: int, max_value: int) -> Optional[int]:
    try:
        answer = questionary.text(f"{message} (Current: {default_value}, Range: {min_value}-{max_value})").ask()
        if answer is None:
            return None
        answer = answer.strip()
        if answer == "":
            return default_value
        value = int(float(answer))
        if value < min_value:
            value = min_value
        if value > max_value:
            value = max_value
        return value
    except Exception:
        return None

def show_models_menu() -> Optional[str]:
    """Shows the Manage AI Models menu."""
    last_choice = None
    while True:
        try:
            current_model_id = config.get('transcription.model_id')
            current_model_name = prettify(current_model_id) if current_model_id else "Not Set"

            choices = [
                questionary.Choice("Download/Install Models", value="download"),
                questionary.Choice("Install Custom Model by ID", value="custom"),
                questionary.Choice(f"Set Active Model (Current: {current_model_name})", value="set_active"),
                questionary.Choice("Refresh Model List", value="refresh"),
                questionary.Separator(),
                questionary.Choice("Back to Settings", value="back")
            ]

            choice = questionary.select("Manage AI Models", choices=choices, use_indicator=True, default=last_choice).ask()

            if choice is None or choice == "back":
                break

            last_choice = choice

            if choice == "download":
                console.print("\n[bold]Download Models[/bold]")
                print_info("Fetching available Whisper models from Hugging Face...")

                models = fetch_available_whisper_models()
                if not models:
                    print_error("Could not fetch models from Hugging Face. Check your internet connection.")
                    continue

                download_choices = []
                for model in models:
                    installed_marker = " [Installed]" if is_installed(model['id']) else ""
                    download_choices.append(questionary.Choice(
                        title=f"{model['name']}{installed_marker}",
                        value=model['id']
                    ))

                selected_models = questionary.checkbox(
                    "Select models to download (use Space to select, Enter to confirm):",
                    choices=download_choices
                ).ask()

                if selected_models:
                    console.print(f"\n[bold]Downloading {len(selected_models)} model(s)...[/bold]\n")
                    for model_id in selected_models:
                        if is_installed(model_id):
                            print_info(f"Skipping {prettify(model_id)} (already installed)")
                            continue

                        print_info(f"Downloading {prettify(model_id)}...")
                        if download_model(model_id):
                            print_success(f"Downloaded {prettify(model_id)}")
                        else:
                            print_error(f"Failed to download {prettify(model_id)}")

            elif choice == "custom":
                console.print("\n[bold]Install Custom Model[/bold]")
                custom_id = questionary.text("Enter the Hugging Face model ID (e.g. primeline/whisper-large-v3-german):").ask()

                if custom_id:
                    custom_id = custom_id.strip()
                    print_info(f"Checking compatibility for '{custom_id}'...")
                    is_compatible, reason = check_compatibility(custom_id)

                    if is_compatible:
                        print_success(f"Model '{custom_id}' is compatible.")
                        if questionary.confirm(f"Do you want to download and install '{custom_id}' now?").ask():
                            print_info(f"Downloading {custom_id}...")
                            if download_model(custom_id):
                                print_success(f"Downloaded {custom_id}")
                                if questionary.confirm(f"Set '{custom_id}' as the active model?").ask():
                                    return custom_id
                            else:
                                print_error(f"Failed to download {custom_id}")
                    else:
                        print_error(f"Model '{custom_id}' is likely incompatible or invalid.\nReason: {reason}")

            elif choice == "set_active":
                new_model_id = select_active_model()
                if new_model_id and new_model_id != current_model_id:
                    return new_model_id

            elif choice == "refresh":
                print_info("Refreshing model list from Hugging Face...")
                models = fetch_available_whisper_models()
                if models:
                    print_success(f"Found {len(models)} available models.")
                else:
                    print_error("Could not fetch models from Hugging Face.")

        except (KeyboardInterrupt, TypeError):
            break

    return None

def show_audio_settings_menu():
    last_choice = None
    while True:
        try:
            trim_start = config.get('audio.trim_start_ms') or 0
            trim_end = config.get('audio.trim_end_ms') or 0
            min_ms = config.get('audio.min_recording_ms') or 0

            choices = [
                questionary.Choice(f"Trim start (ms): {trim_start}", value="trim_start"),
                questionary.Choice(f"Trim end (ms): {trim_end}", value="trim_end"),
                questionary.Choice(f"Minimum duration (ms): {min_ms}", value="min_ms"),
                questionary.Separator(),
                questionary.Choice("Back", value="back")
            ]

            choice = questionary.select("Audio Settings", choices=choices, use_indicator=True, default=last_choice).ask()
            if choice is None or choice == "back":
                break

            last_choice = choice

            if choice == "trim_start":
                new_val = _prompt_int_in_range("Enter trim at start in ms", trim_start, 0, 5000)
                if new_val is not None:
                    config.set('audio.trim_start_ms', new_val)
                    print_success(f"Trim start set to {new_val} ms.")
            elif choice == "trim_end":
                new_val = _prompt_int_in_range("Enter trim at end in ms", trim_end, 0, 5000)
                if new_val is not None:
                    config.set('audio.trim_end_ms', new_val)
                    print_success(f"Trim end set to {new_val} ms.")
            elif choice == "min_ms":
                new_val = _prompt_int_in_range("Enter minimum recording length in ms", min_ms, 0, 10000)
                if new_val is not None:
                    config.set('audio.min_recording_ms', new_val)
                    print_success(f"Minimum recording set to {new_val} ms.")
        except (KeyboardInterrupt, TypeError):
            break

def show_settings_menu() -> Optional[str]:
    console.print("\n")
    console.print(Panel("[bold cyan]Settings Menu[/bold cyan]", expand=False, border_style="cyan"))

    last_choice = None
    while True:
        try:
            # Determine effective translation state for display label
            _translate_flag = config.get('transcription.translate_to_english') or False
            _task_cfg = config.get('transcription.task')
            _effective_translate = bool(_translate_flag or (_task_cfg == 'translate'))

            # Get clipboard and auto-type settings with defaults
            _copy_to_clipboard = config.get('transcription.copy_to_clipboard')
            if _copy_to_clipboard is None:
                _copy_to_clipboard = True
            _type_into_active_field = config.get('transcription.type_into_active_field')
            if _type_into_active_field is None:
                _type_into_active_field = True
            _type_mode = config.get('transcription.type_mode')
            if _type_mode is None:
                _type_mode = 'direct'
            _type_mode_display = "Direct typing" if _type_mode == 'direct' else "Paste (Ctrl+V)"

            choice = questionary.select(
                "What would you like to change?",
                choices=[
                    "Change Transcription Language",
                    "Manage AI Models",
                    "Change Hotkey Settings",
                    "Change Audiorecord Settings",
                    f"Translate to English: {'On' if _effective_translate else 'Off'}",
                    f"Type into active field: {'On' if _type_into_active_field else 'Off'}",
                    f"Typing mode: {_type_mode_display}",
                    f"Copy to clipboard: {'On' if _copy_to_clipboard else 'Off'}",
                    "Back to App"
                ], use_indicator=True, default=last_choice
            ).ask()

            if choice is None or choice == "Back to App":
                console.print("\n[bold green]✓ Settings updated. Resuming application...[/bold green]\n")
                print_ready_message()
                return None

            last_choice = choice

            if choice == "Change Transcription Language":
                new_language = select_language()
                if new_language:
                    config.set('transcription.language', new_language)
                    console.print("\n[bold green]✓ Language changed. Returning to application...[/bold green]\n")
                    print_ready_message()
                    return None

            elif choice == "Manage AI Models":
                new_model_id = show_models_menu()
                if new_model_id and new_model_id != config.get('transcription.model_id'):
                    print_info("Changing the model requires reloading. This may take a moment.")
                    return new_model_id

            elif choice == "Change Hotkey Settings":
                show_hotkey_settings_menu()
                print_ready_message()

            elif choice == "Change Audiorecord Settings":
                show_audio_settings_menu()
                print_ready_message()

            elif choice and choice.startswith("Translate to English:"):
                # Toggle translation flag and keep legacy 'task' in sync
                _translate_flag = config.get('transcription.translate_to_english') or False
                _task_cfg = config.get('transcription.task')
                _effective_translate = bool(_translate_flag or (_task_cfg == 'translate'))

                new_val = not _effective_translate
                config.set('transcription.translate_to_english', new_val)
                config.set('transcription.task', 'translate' if new_val else 'transcribe')
                print_success(f"Translate to English set to {'On' if new_val else 'Off'}.")
                print_ready_message()

            elif choice and choice.startswith("Copy to clipboard:"):
                _copy_to_clipboard = config.get('transcription.copy_to_clipboard')
                if _copy_to_clipboard is None:
                    _copy_to_clipboard = True
                _type_mode = config.get('transcription.type_mode')
                if _type_mode is None:
                    _type_mode = 'direct'
                new_val = not _copy_to_clipboard
                config.set('transcription.copy_to_clipboard', new_val)
                # If turning off clipboard while paste mode is active, switch to direct mode
                if not new_val and _type_mode == 'paste':
                    config.set('transcription.type_mode', 'direct')
                    print_success(f"Copy to clipboard set to Off. Typing mode automatically switched to Direct (Paste mode requires clipboard).")
                else:
                    print_success(f"Copy to clipboard set to {'On' if new_val else 'Off'}.")
                print_ready_message()

            elif choice and choice.startswith("Type into active field:"):
                _type_into_active_field = config.get('transcription.type_into_active_field')
                if _type_into_active_field is None:
                    _type_into_active_field = True
                new_val = not _type_into_active_field
                config.set('transcription.type_into_active_field', new_val)
                print_success(f"Type into active field set to {'On' if new_val else 'Off'}.")
                print_ready_message()

            elif choice and choice.startswith("Typing mode:"):
                current_mode = config.get('transcription.type_mode')
                if current_mode is None:
                    current_mode = 'direct'
                new_mode = questionary.select(
                    "Select typing mode:",
                    choices=[
                        questionary.Choice("Direct typing (type characters)", value="direct"),
                        questionary.Choice("Paste via Ctrl+V from clipboard", value="paste")
                    ],
                    default="direct" if current_mode == 'direct' else "paste"
                ).ask()
                if new_mode:
                    config.set('transcription.type_mode', new_mode)
                    # If paste mode is selected, ensure clipboard is enabled
                    if new_mode == 'paste':
                        _copy_to_clipboard = config.get('transcription.copy_to_clipboard')
                        if _copy_to_clipboard is None or not _copy_to_clipboard:
                            config.set('transcription.copy_to_clipboard', True)
                            print_success(f"Typing mode set to: Paste (Ctrl+V). Copy to clipboard automatically enabled (required for paste mode).")
                        else:
                            print_success(f"Typing mode set to: Paste (Ctrl+V).")
                    else:
                        mode_display = "Direct typing"
                        print_success(f"Typing mode set to: {mode_display}.")
                    print_ready_message()

        except (KeyboardInterrupt, TypeError):
            console.print("\n[bold green]✓ Settings updated. Resuming application...[/bold green]\n")
            print_ready_message()
            return None