from typing import Dict, Any, Optional
from backend.services.language_adapters import (
    detect_language, MultilingualXLMRoBERTaAdapter, IndicLanguageAdapter, BaseLanguageAdapter
)
from backend.services.voice_stress import VoiceStressAnalyzer

class NLPEmotionPipeline:
    """Standalone modular NLP & Audio Emotion AI Pipeline Service.
    
    Accepts text input (Chatbot, SMS, Web) and audio input (IVRS calls),
    performing multilingual sentiment analysis, emotion classification,
    and acoustic voice stress analysis.
    """

    def __init__(self):
        self.multilingual_adapter = MultilingualXLMRoBERTaAdapter()
        self.indic_adapters: Dict[str, BaseLanguageAdapter] = {
            "ta": IndicLanguageAdapter("ta"),
            "te": IndicLanguageAdapter("te"),
            "mr": IndicLanguageAdapter("mr"),
            "bn": IndicLanguageAdapter("bn")
        }

    def _get_adapter(self, lang: str) -> BaseLanguageAdapter:
        if lang in self.indic_adapters:
            return self.indic_adapters[lang]
        return self.multilingual_adapter

    def analyze_text(self, text: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Analyze raw text input (from Chatbot, SMS, or Web Portal).
        
        Returns normalized JSON schema:
        {
          "sentiment_score": float,
          "sentiment_label": str,
          "emotion_labels": dict,
          "voice_stress_score": null,
          "acoustic_features": null,
          "language": str,
          "confidence": float
        }
        """
        if not text or not text.strip():
            return {
                "sentiment_score": 0.0,
                "sentiment_label": "neutral",
                "emotion_labels": {"fear": 0.0, "anxiety": 0.0, "sadness": 0.0, "anger": 0.0, "neutral": 1.0},
                "voice_stress_score": None,
                "acoustic_features": None,
                "language": language or "en",
                "confidence": 1.0
            }

        lang = language or detect_language(text)
        adapter = self._get_adapter(lang)

        sentiment_score, sentiment_label, confidence = adapter.analyze_sentiment(text)
        emotion_labels = adapter.classify_emotions(text)

        return {
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "emotion_labels": emotion_labels,
            "voice_stress_score": None,
            "acoustic_features": None,
            "language": lang,
            "confidence": confidence
        }

    def analyze_audio(
        self,
        audio_bytes: bytes,
        transcript_text: Optional[str] = None,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze audio stream (from IVRS call) with acoustic voice stress & transcript sentiment.
        
        Returns normalized JSON schema:
        {
          "sentiment_score": float,
          "sentiment_label": str,
          "emotion_labels": dict,
          "voice_stress_score": float,
          "acoustic_features": dict,
          "language": str,
          "confidence": float
        }
        """
        text = transcript_text or ""
        lang = language or detect_language(text)
        adapter = self._get_adapter(lang)

        # 1. Text Sentiment & Emotion
        sentiment_score, sentiment_label, text_confidence = adapter.analyze_sentiment(text)
        emotion_labels = adapter.classify_emotions(text)

        # 2. Acoustic Voice Stress Extraction
        word_count = len(text.split()) if text else None
        stress_res = VoiceStressAnalyzer.analyze_audio(audio_bytes, transcript_word_count=word_count)

        voice_stress_score = stress_res.get("voice_stress_score")
        acoustic_features = {
            "pitch_variance": stress_res.get("pitch_variance", 0.0),
            "speech_rate_wps": stress_res.get("speech_rate_wps", 0.0),
            "pause_ratio": stress_res.get("pause_ratio", 0.0)
        }

        # 3. Blended Confidence Metric
        confidence = round((text_confidence + (0.85 if voice_stress_score is not None else 0.50)) / 2.0, 2)

        return {
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "emotion_labels": emotion_labels,
            "voice_stress_score": voice_stress_score,
            "acoustic_features": acoustic_features,
            "language": lang,
            "confidence": confidence
        }

# Global singleton instance for easy import across Chatbot, IVRS, and SMS services
pipeline_service = NLPEmotionPipeline()
nlp_pipeline = pipeline_service
