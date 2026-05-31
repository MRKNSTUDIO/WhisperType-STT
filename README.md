# WhisperType

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](#requirements)
[![Status: Beta](https://img.shields.io/badge/Status-Beta%20v0.3.0-orange.svg)](#known-issues--limitations)

**WhisperType** is a local, offline speech-to-text assistant for Windows. Press a
hotkey, speak, and your words are transcribed by [OpenAI Whisper](https://github.com/openai/whisper)
and typed (or pasted) straight into whatever app you're using - your editor,
browser, chat, anything. Everything runs on your own machine; your audio never
leaves your computer.

> **Heads-up: this is an early beta (v0.3.0) and is not perfect.** A few things
> are still rough or broken - please read [Known Issues & Limitations](#known-issues--limitations)
> before you rely on it.

---

## Features

- **Global hotkey recording** - works in any application, system-wide.
- **Two recording modes** - *Toggle* (press once to start, again to stop) or
  *Push-to-Talk* (hold a key while speaking).
- **Types or pastes for you** - direct keystroke typing or clipboard paste (Ctrl+V).
- **90+ languages** plus optional **translate-to-English**.
- **Runs locally on your GPU or CPU** - powered by NVIDIA CUDA when available.
- **Built-in model manager** - download, switch, and manage Whisper models from a
  friendly terminal menu.
- **Copy to clipboard** option for transcriptions.

---

## Requirements

- **Windows 10/11** (the app uses Windows-only features such as `winsound`).
- **64-bit Python 3.11** - [python.org/downloads](https://www.python.org/downloads/).
  Tick *"Add Python to PATH"* during install.
- A **microphone**.
- *(Optional, recommended)* an **NVIDIA GPU** for fast transcription. No GPU?
  It still works on CPU, just slower.

---

## Choosing matching Python + CUDA + PyTorch versions (read this first!)

This is the #1 thing people get wrong. Three pieces have to agree with each
other, or PyTorch will refuse to use your GPU (or fail to install):

1. **Your Python version**
2. **Your NVIDIA driver's CUDA version**
3. **The PyTorch build you install**

Think of it like a power plug: the shape has to match the socket. Here's how to
get it right in a couple of minutes.

### Step 1 - Find your CUDA version

Open the Start menu, type `cmd`, press Enter, then run:

```cmd
nvidia-smi
```

In the **top-right corner** you'll see something like `CUDA Version: 12.4`.
That number is the **highest** CUDA version your driver supports.

> No NVIDIA GPU, or `nvidia-smi` is not recognized? That's fine - you'll use the
> **CPU** build (see Step 2).

### Step 2 - Get the right PyTorch command

Go to **[pytorch.org](https://pytorch.org/)** and scroll to the **"Install PyTorch"**
box. Select:

| Option           | Pick                                                            |
| ---------------- | --------------------------------------------------------------- |
| PyTorch Build    | **Stable**                                                      |
| Your OS          | **Windows**                                                     |
| Package          | **Pip**                                                         |
| Language         | **Python**                                                      |
| Compute Platform | the **CUDA version equal to or lower** than your `nvidia-smi` number (or **CPU** if you have no GPU) |

The page generates a command like:

```cmd
pip3 install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
```

Copy that command - you'll be able to paste it into the installer (option `[2]`).

### Step 3 - Use Python 3.11

Newer Python versions sometimes don't have matching PyTorch builds yet. **Python
3.11 (64-bit)** is the safe, well-supported choice for this app.

### The short version

- `nvidia-smi` shows the **max** CUDA your driver allows.
- On [pytorch.org](https://pytorch.org/), pick a CUDA **equal to or lower** than that.
- Stick to **Python 3.11 64-bit**.
- No GPU? Choose **CPU** everywhere.

The installer (`install.ps1`) tries to pick a sensible default automatically, but
if you want full control, just paste the exact command from pytorch.org when it
asks.

---

## Installation

1. Download or clone this repository:

```cmd
git clone https://github.com/MRKNSTUDIO/WhisperType-STT.git
cd WhisperType-STT
```

2. Run the installer. Either **right-click `install.ps1` -> "Run with PowerShell"**,
   or from a terminal:

```cmd
powershell -ExecutionPolicy Bypass -File install.ps1
```

The installer will:

- detect your Python installations and let you pick one,
- create an isolated virtual environment (`venv/`),
- install **PyTorch** (it detects your GPU and recommends a build, or lets you
  paste your own command from pytorch.org, or installs the CPU build),
- install the remaining dependencies from `requirements.txt`,
- optionally pre-download Whisper models.

> **Why `-ExecutionPolicy Bypass`?** By default Windows blocks running
> `.ps1` scripts. This flag allows this one script to run without changing any
> system-wide settings.

---

## Usage

Start the app by **right-clicking `run.ps1` -> "Run with PowerShell"**, or:

```cmd
powershell -ExecutionPolicy Bypass -File run.ps1
```

On first launch you'll be guided through picking a Whisper model and your
language. After that, the default hotkeys are:

| Action            | Default key   |
| ----------------- | ------------- |
| Start/stop record | **Scroll Lock** (Toggle mode) |
| Open settings     | **F1**        |
| Quit              | **Ctrl + Q**  |

Speak while recording, and the transcription is typed into the currently focused
field. Open the settings menu (F1) to change language, model, recording mode,
typing/paste behavior, translation, and audio trimming.

---

## Configuration

Settings are stored in `user_config.json` in the project root. It is created
automatically with sensible defaults on first run, and most options are editable
from the in-app settings menu (F1). Useful keys:

- `hotkeys.hotkey_mode` - `"toggle"` or `"pushtotalk"`
- `hotkeys.toggle_key` / `hotkeys.pushtotalk_key` - the recording key
- `transcription.model_id` - active Whisper model
- `transcription.language` - input language
- `transcription.type_mode` - `"direct"` or `"paste"`

---

## Known Issues & Limitations

This is a **beta** tool built for personal use - it works, but it's not polished
and a few things are broken:

- **Setting a new recording hotkey from the in-app settings (F1) does not work
  reliably.** The menu's Enter key can get captured instead of your intended key.
  **Workaround:** close the app and edit `user_config.json` directly - set
  `hotkeys.toggle_key` (e.g. `"scroll lock"`) or `hotkeys.pushtotalk_key`.
- **No "is a text field focused?" check.** Transcribed text is typed wherever the
  OS focus currently is. If no text field is focused (for example you're on the
  desktop), the keystrokes still fire and can trigger shortcuts. Make sure your
  cursor is in a real text field before recording.
- **Windows only.** The app relies on Windows-specific APIs (`winsound`, `msvcrt`)
  and is untested on macOS/Linux.
- **First model download is large** and needs an internet connection. CPU
  transcription is noticeably slower than GPU.
- Some keyboards/layouts may report keys differently, which can affect hotkey
  detection.

Bug reports and PRs are welcome.

---

## Project structure

```
WhisperType-STT/
├── README.md
├── LICENSE                 # MIT
├── requirements.txt
├── install.ps1             # one-step setup (venv + PyTorch + deps + models)
├── run.ps1                 # launches the app
└── src/
    ├── main.py             # app entry point + hotkey loop
    ├── tui.py              # terminal UI, menus, settings
    ├── config_manager.py   # loads/saves user_config.json
    ├── transcriber.py      # Whisper model loading + inference
    ├── audio_handler.py    # microphone recording (PyAudio)
    ├── hardware_manager.py # CUDA/CPU device detection
    ├── model_fetcher.py    # Hugging Face model discovery/download
    ├── predownload_models.py
    └── version.py
```

---

## Acknowledgements

- [OpenAI Whisper](https://github.com/openai/whisper) for the speech-to-text models.
- [Hugging Face](https://huggingface.co/) `transformers` and `huggingface_hub`.
- [PyTorch](https://pytorch.org/), [Rich](https://github.com/Textualize/rich),
  and [Questionary](https://github.com/tmbo/questionary).

---

## License

Released under the [MIT License](LICENSE). © 2026 MRKNSTUDIO.
