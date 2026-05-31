# hardware_manager.py
import torch
import tui

def get_device() -> torch.device:
    """
    Detects and returns the best available device (CUDA, MPS, CPU).
    """
    tui.print_info("Hardware Detection...")

    if torch.cuda.is_available():
        device = torch.device("cuda")
        tui.print_success(f"CUDA available. Using GPU: {torch.cuda.get_device_name(0)}")
    else:
        device = torch.device("cpu")
        tui.print_info("No GPU acceleration (CUDA) found. Using CPU.")
        tui.console.print("   [yellow]Note: Transcription will be slower.[/yellow]")

    return device