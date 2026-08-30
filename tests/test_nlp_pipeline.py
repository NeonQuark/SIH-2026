import io
import wave
import struct
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.nlp_pipeline import NLPEmotionPipeline, pipeline_service
from backend.services.voice_stress import VoiceStressAnalyzer

client = TestClient(app)

def create_synthetic_wav_bytes(duration_sec: float = 2.0, sample_rate: int = 16000) -> bytes:
    """Helper to generate valid in-memory PCM WAV bytes for acoustic analysis tests."""
    buf = io.BytesIO()
    n_samples = int(duration_sec * sample_rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        
        # Generate alternating tones and silent pauses
        samples = []
        for i in range(n_samples):
            if (i // 1600) % 2 == 0:
                val = int(10000 * math.sin(2 * math.pi * 440 * i / sample_rate))
            else:
                val = 0
            samples.append(val)
            
        raw_bytes = struct.pack(f"<{n_samples}h", *samples)
        wf.writeframes(raw_bytes)
    return buf.getvalue()

import math

def test_nlp_text_analysis_english_distress():
    pipeline = NLPEmotionPipeline()
    res = pipeline.analyze_text("I am feeling very scared and unsafe, please help me", language="en")
    
    assert res["language"] == "en"
    assert res["sentiment_label"] == "negative"
    assert res["sentiment_score"] < 0.0
    assert res["emotion_labels"]["fear"] > 0.20
    assert res["voice_stress_score"] is None
    assert res["acoustic_features"] is None
    assert "confidence" in res

def test_nlp_text_analysis_hindi_distress():
    pipeline = NLPEmotionPipeline()
    res = pipeline.analyze_text("मुझे बहुत डर लग रहा है और सुरक्षा का खतरा है")
    
    assert res["language"] == "hi"
    assert res["sentiment_label"] == "negative"
    assert res["emotion_labels"]["fear"] > 0.20
    assert res["voice_stress_score"] is None

def test_voice_stress_analyzer_synthetic_audio():
    wav_bytes = create_synthetic_wav_bytes(duration_sec=3.0)
    res = VoiceStressAnalyzer.analyze_audio(wav_bytes, transcript_word_count=12)
    
    assert "pitch_variance" in res
    assert "speech_rate_wps" in res
    assert "pause_ratio" in res
    assert "voice_stress_score" in res
    assert 0.0 <= res["voice_stress_score"] <= 1.0

def test_nlp_audio_pipeline_integration():
    wav_bytes = create_synthetic_wav_bytes(duration_sec=2.5)
    res = pipeline_service.analyze_audio(
        audio_bytes=wav_bytes,
        transcript_text="I am in danger and terrified",
        language="en"
    )
    
    assert res["sentiment_label"] == "negative"
    assert res["emotion_labels"]["fear"] > 0.10
    assert res["voice_stress_score"] is not None
    assert res["acoustic_features"]["pitch_variance"] >= 0.0
    assert res["acoustic_features"]["speech_rate_wps"] >= 0.0
    assert res["acoustic_features"]["pause_ratio"] >= 0.0

def test_api_nlp_analyze_text_endpoint():
    payload = {"text": "I feel anxious and overwhelmed", "language": "en"}
    res = client.post("/api/nlp/analyze-text", json=payload)
    
    assert res.status_code == 200
    data = res.json()
    assert data["sentiment_label"] == "negative"
    assert "emotion_labels" in data
    assert data["language"] == "en"

def test_api_nlp_analyze_audio_endpoint():
    wav_bytes = create_synthetic_wav_bytes(duration_sec=2.0)
    files = {"file": ("test_call.wav", wav_bytes, "audio/wav")}
    data = {"transcript_text": "Help me please", "language": "en"}
    
    res = client.post("/api/nlp/analyze-audio", files=files, data=data)
    assert res.status_code == 200
    out = res.json()
    assert out["voice_stress_score"] is not None
    assert "acoustic_features" in out
    assert out["sentiment_label"] == "negative"
