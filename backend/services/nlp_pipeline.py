from typing import Dict, Any, Optional
from backend.services.language_adapters import (
    detect_language, MultilingualXLMRoBERTaAdapter, IndicLanguageAdapter, BaseLanguageAdapter
)
from backend.services.voice_stress import VoiceStressAnalyzer

HARD_TRIGGER_TERMS = [
    # 1. Self-Harm & Suicidal Ideation
    "kill myself", "end it", "end it all", "no point living", "khatam kar dena", "marna chahta",
    "marne", "suicide", "end my life", "better off without me", "no point continuing",
    "dying", "want to die", "mar jaunga", "jaan de dunga", "no escape from them except dying",
    "don't want to wake up",
    
    # 2. Explicit Weapon Mentions
    "knife", "gun", "chaku", "pistol", "bandook", "iron rod", "iron rods", "sword", "acid", "firearm", "weapon",
    
    # 3. Explicit Violence Threats
    "will kill you", "marunga", "jaan se maar dunga", "threatened to kill", "grabbed my neck", "throat",
    "gundey", "beat me", "break your legs", "murder", "harm", "hathiyaar",
    
    # 4. Immediate Physical Danger Phrases
    "he's outside", "someone's breaking in", "koi ghar mein ghus raha hai", "door pe kisi ne",
    "standing outside", "following me", "peecha kar raha", "outside my window", "bad man came", "chasing me",
    "observing my residence", "approached my premises"
]

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
        """Analyze raw text input (from Chatbot, SMS, or Web Portal)."""
        if not text or not text.strip():
            return {
                "sentiment_score": 0.0,
                "sentiment_label": "neutral",
                "emotion_labels": {"fear": 0.0, "anxiety": 0.0, "sadness": 0.0, "anger": 0.0, "neutral": 1.0},
                "voice_stress_score": None,
                "acoustic_features": None,
                "language": language or "en",
                "confidence": 1.0,
                "hard_trigger_detected": False,
                "hard_trigger_matched_terms": [],
                "low_confidence_review_needed": False
            }

        lang = language or detect_language(text)
        adapter = self._get_adapter(lang)

        sentiment_score, sentiment_label, confidence = adapter.analyze_sentiment(text)
        emotion_labels = adapter.classify_emotions(text)

        # Hard-trigger safety override evaluation
        text_lower = text.lower()
        matched_triggers = [t for t in HARD_TRIGGER_TERMS if t in text_lower]
        hard_trigger_detected = len(matched_triggers) > 0

        if hard_trigger_detected:
            sentiment_score = -1.0
            sentiment_label = "negative"
            emotion_labels["fear"] = max(emotion_labels.get("fear", 0.0), 0.85)

        low_confidence_review_needed = confidence < 0.50

        return {
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "emotion_labels": emotion_labels,
            "voice_stress_score": None,
            "acoustic_features": None,
            "language": lang,
            "confidence": confidence,
            "hard_trigger_detected": hard_trigger_detected,
            "hard_trigger_matched_terms": matched_triggers,
            "low_confidence_review_needed": low_confidence_review_needed
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
