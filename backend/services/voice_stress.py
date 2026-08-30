import io
import math
import struct
import wave
from typing import Dict, Any, Optional

class VoiceStressAnalyzer:
    """Acoustic signal analyzer for voice stress detection from audio input."""

    @classmethod
    def analyze_audio(cls, audio_bytes: bytes, transcript_word_count: Optional[int] = None) -> Dict[str, Any]:
        """Extract voice stress indicators: pitch variance, speech rate, pause patterns.
        
        Returns:
            Dict containing pitch_variance, speech_rate_wps, pause_ratio, and voice_stress_score.
        """
        if not audio_bytes or len(audio_bytes) < 44:
            # Fallback for synthetic/empty audio buffers
            return {
                "pitch_variance": 0.0,
                "speech_rate_wps": 0.0,
                "pause_ratio": 0.0,
                "voice_stress_score": None
            }

        try:
            # Attempt to parse WAV format header
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                sample_rate = wf.getframerate()
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                n_frames = wf.getnframes()
                frames = wf.readframes(n_frames)

            duration_sec = n_frames / float(sample_rate) if sample_rate else 1.0
            if duration_sec <= 0:
                duration_sec = 1.0

            # Convert bytes to sample array
            fmt = f"<{n_frames * n_channels}{'h' if sample_width == 2 else 'b'}"
            samples = struct.unpack(fmt, frames)
            if n_channels > 1:
                samples = samples[::n_channels]

        except Exception:
            # If raw PCM or non-WAV bytes, perform fallback energy estimation
            duration_sec = max(1.0, len(audio_bytes) / 16000.0)
            samples = [int(b) - 128 for b in audio_bytes[::4]]

        # 1. Energy Frame Analysis & Pause Ratio
        frame_size = 320  # ~20ms at 16kHz
        frames_energy = []
        silent_frames = 0
        total_frames = max(1, len(samples) // frame_size)

        for i in range(total_frames):
            chunk = samples[i * frame_size: (i + 1) * frame_size]
            rms = math.sqrt(sum(s * s for s in chunk) / max(1, len(chunk)))
            frames_energy.append(rms)
            if rms < 50:  # Threshold for silence/pause
                silent_frames += 1

        pause_ratio = round(silent_frames / float(total_frames), 3)

        # 2. Pitch Variance (F0 Spectral Energy Volatility Approximation)
        if len(frames_energy) > 1:
            mean_energy = sum(frames_energy) / len(frames_energy)
            variance = sum((e - mean_energy) ** 2 for e in frames_energy) / len(frames_energy)
            pitch_variance = round(math.sqrt(variance), 2)
        else:
            pitch_variance = 0.0

        # 3. Speech Rate (words per second)
        if transcript_word_count and transcript_word_count > 0:
            speech_rate_wps = round(transcript_word_count / duration_sec, 2)
        else:
            # Estimate word bursts based on non-silent energy transitions
            bursts = sum(1 for i in range(1, len(frames_energy)) if frames_energy[i] >= 50 and frames_energy[i-1] < 50)
            speech_rate_wps = round(max(0.5, bursts / duration_sec), 2)

        # 4. Composite Voice Stress Score (0.0 to 1.0)
        # Higher stress correlated with high pitch variance, elevated speech rate (> 3.5 wps), and short abrupt pauses
        stress_pitch_component = min(1.0, pitch_variance / 300.0)
        stress_rate_component = min(1.0, max(0.0, (speech_rate_wps - 1.5) / 3.5))
        stress_pause_component = min(1.0, max(0.0, (pause_ratio - 0.15) / 0.50))

        voice_stress_score = round(
            0.45 * stress_pitch_component +
            0.35 * stress_rate_component +
            0.20 * stress_pause_component,
            2
        )
        voice_stress_score = max(0.0, min(1.0, voice_stress_score))

        return {
            "pitch_variance": pitch_variance,
            "speech_rate_wps": speech_rate_wps,
            "pause_ratio": pause_ratio,
            "voice_stress_score": voice_stress_score
        }
