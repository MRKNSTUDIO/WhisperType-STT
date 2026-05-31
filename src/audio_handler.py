# audio_handler.py
import tui
from config_manager import config
import platform

# Optional Windows sound support
try:
    import winsound as _winsound
    _WINSOUND_AVAILABLE = True
except Exception:
    _winsound = None
    _WINSOUND_AVAILABLE = False

# Import PyAudio for Windows audio recording
try:
    import pyaudio as _pyaudio
    PYAUDIO_FORMAT = getattr(_pyaudio, config.get('audio.pyaudio_format'))
    PYAUDIO_AVAILABLE = True
except Exception:
    _pyaudio = None
    PYAUDIO_FORMAT = None
    PYAUDIO_AVAILABLE = False

def play_notification_sound(event_type: str = "start") -> None:
    """Plays gentle notification beeps on Windows; prints fallback otherwise."""
    try:
        if platform.system() == "Windows" and _WINSOUND_AVAILABLE:
            if event_type == "start":
                _winsound.Beep(600, 40)
                _winsound.Beep(800, 40)
            elif event_type == "stop":
                _winsound.Beep(800, 40)
                _winsound.Beep(600, 40)
            elif event_type == "error":
                _winsound.Beep(400, 100)
                _winsound.Beep(300, 100)
        else:
            if event_type == "start":
                tui.print_info("[Audio] Recording Start")
            elif event_type == "stop":
                tui.print_info("[Audio] Recording Stop")
            elif event_type == "error":
                tui.print_error("[Audio] Error")
    except Exception as e:
        tui.print_error(f"Could not play notification sound: {e}")


if PYAUDIO_AVAILABLE:
    class AudioRecorder:
        def __init__(self):
            self.pyaudio_instance = None
            self.stream = None
            self.is_recording = False
            self.audio_buffer = []
            self.mic_sample_rate = 0

        def start_recording(self):
            """Initializes PyAudio and starts the recording stream."""
            if self.is_recording:
                return

            self.is_recording = True
            self.audio_buffer = []

            try:
                self.pyaudio_instance = _pyaudio.PyAudio()
                device_info = self.pyaudio_instance.get_default_input_device_info()
                self.mic_sample_rate = int(device_info['defaultSampleRate'])

                self.stream = self.pyaudio_instance.open(
                    format=PYAUDIO_FORMAT,
                    channels=config.get('audio.channels'),
                    rate=self.mic_sample_rate,
                    input=True,
                    frames_per_buffer=config.get('audio.chunk_size'),
                    input_device_index=device_info['index'],
                    stream_callback=self._audio_callback
                )
                play_notification_sound("start")
                tui.print_info("--- Recording ACTIVE ---")
            except Exception as e:
                tui.print_error(f"Could not open microphone stream: {e}")
                play_notification_sound("error")
                self.is_recording = False
                self._cleanup()

        def _audio_callback(self, in_data, frame_count, time_info, status):
            """This function is called by PyAudio for each new chunk of audio."""
            self.audio_buffer.append(in_data)
            return (in_data, _pyaudio.paContinue)

        def stop_recording(self) -> list:
            """Stops the recording and returns the collected audio buffer."""
            if not self.is_recording:
                return []

            self.is_recording = False
            play_notification_sound("stop")
            tui.print_info("--- Recording STOPPED ---")

            self._cleanup()
            return self.audio_buffer

        def _cleanup(self):
            """Safely closes the PyAudio stream and instance."""
            try:
                if self.stream and self.stream.is_active():
                    self.stream.stop_stream()
                if self.stream:
                    self.stream.close()
                if self.pyaudio_instance:
                    self.pyaudio_instance.terminate()
            except Exception as e:
                tui.print_error(f"Error while closing audio stream: {e}")
            finally:
                self.stream = None
                self.pyaudio_instance = None
else:
    class AudioRecorder:
        def __init__(self):
            self.is_recording = False
            self.audio_buffer = []
            self.mic_sample_rate = 0

        def start_recording(self):
            tui.print_error("PyAudio is not available. Please install PyAudio for Windows audio recording.")
            play_notification_sound("error")
            self.is_recording = False

        def stop_recording(self) -> list:
            return []

        def _cleanup(self):
            pass