from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.db.session import SessionLocal
from backend.db.models import DistressScore, VictimProfile

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class DynamicDistressEngine:
    """Dynamic Distress Score Engine with Explainable Feature Attribution & Longitudinal Trend Storage.
    
    Computes a weighted composite score (0-100) combining NLP inputs (sentiment, emotion, voice stress)
    and behavioral signals (engagement frequency, missed check-ins, response latency, drop-off rate).
    """

    # Tunable composite weights summing to 1.0 (Max composite score = 100.0)
    DEFAULT_WEIGHTS = {
        "fear_emotion": 0.20,
        "anxiety_emotion": 0.15,
        "negative_sentiment": 0.15,
        "voice_stress": 0.15,
        "missed_checkins": 0.15,
        "response_latency": 0.10,
        "drop_off_rate": 0.10,
    }

    def __init__(self, custom_weights: Optional[Dict[str, float]] = None):
        self.weights = custom_weights or dict(self.DEFAULT_WEIGHTS)
        # Normalize weights to sum to 1.0
        total_w = sum(self.weights.values())
        if total_w > 0:
            self.weights = {k: v / total_w for k, v in self.weights.items()}

    def _normalize_inputs(
        self,
        nlp_output: Dict[str, Any],
        behavioral_signals: Dict[str, Any]
    ) -> Dict[str, float]:
        """Convert raw inputs into 0.0-100.0 sub-scores."""
        # 1. Emotion Scores (0.0 to 1.0 -> 0 to 100)
        emotions = nlp_output.get("emotion_labels") or {}
        fear_val = min(100.0, max(0.0, float(emotions.get("fear", 0.0)) * 100.0))
        anxiety_val = min(100.0, max(0.0, float(emotions.get("anxiety", 0.0)) * 100.0))

        # 2. Sentiment Score (-1.0 to +1.0 -> 0 to 100 distress)
        # -1.0 (most negative) -> 100 distress; +1.0 (most positive) -> 0 distress
        raw_sentiment = float(nlp_output.get("sentiment_score", 0.0))
        sentiment_distress = min(100.0, max(0.0, (1.0 - raw_sentiment) / 2.0 * 100.0))

        # 3. Voice Stress Score (0.0 to 1.0 -> 0 to 100)
        raw_voice_stress = nlp_output.get("voice_stress_score")
        if raw_voice_stress is not None:
            voice_stress_val = min(100.0, max(0.0, float(raw_voice_stress) * 100.0))
        else:
            # Fallback to blended emotion distress if audio is absent
            voice_stress_val = (fear_val + anxiety_val + sentiment_distress) / 3.0

        # 4. Behavioral Signals (If omitted during acute fear/threat intake, baseline scales with fear severity)
        threat_baseline = max(fear_val, sentiment_distress) if (fear_val >= 50.0 or sentiment_distress >= 80.0) else 0.0

        missed = int(behavioral_signals.get("missed_checkins", -1))
        missed_val = min(100.0, (missed / 5.0) * 100.0) if missed >= 0 else threat_baseline

        latency_hrs = behavioral_signals.get("response_latency_hours")
        latency_val = min(100.0, (float(latency_hrs) / 72.0) * 100.0) if latency_hrs is not None else threat_baseline

        drop_off = behavioral_signals.get("drop_off_rate")
        drop_off_val = min(100.0, max(0.0, float(drop_off) * 100.0)) if drop_off is not None else threat_baseline

        return {
            "fear_emotion": fear_val,
            "anxiety_emotion": anxiety_val,
            "negative_sentiment": sentiment_distress,
            "voice_stress": voice_stress_val,
            "missed_checkins": missed_val,
            "response_latency": latency_val,
            "drop_off_rate": drop_off_val,
        }

    def _generate_explainability(
        self,
        sub_scores: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Generate additive rule-based feature attribution explainability.
        
        Calculates exact impact points per factor for zero-hallucination auditability.
        """
        descriptions = {
            "fear_emotion": "Fear & safety threat indicator",
            "anxiety_emotion": "Anxiety & panic level",
            "negative_sentiment": "Text negative sentiment severity",
            "voice_stress": "Acoustic voice stress level",
            "missed_checkins": "Missed check-ins & unresponsiveness",
            "response_latency": "Response latency / inactivity delay",
            "drop_off_rate": "Session drop-off & abandonment rate",
        }

        contributions = []
        for feature, weight in self.weights.items():
            val = sub_scores.get(feature, 0.0)
            impact = round(val * weight, 2)
            contributions.append({
                "feature": feature,
                "impact_points": impact,
                "weight": round(weight, 2),
                "raw_subscore": round(val, 1),
                "description": descriptions.get(feature, feature)
            })

        # Sort descending by impact points
        contributions.sort(key=lambda x: x["impact_points"], reverse=True)
        return contributions

    def _categorize_risk(self, score: float) -> str:
        if score >= 80.0:
            return "Critical"
        elif score >= 65.0:
            return "High"
        elif score >= 35.0:
            return "Moderate"
        else:
            return "Low"

    def compute_longitudinal_trend(
        self,
        victim_id: str,
        window_days: int = 30,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Compute longitudinal distress trend direction over configurable windows (7, 30, 90 days)."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            cutoff = utcnow() - timedelta(days=window_days)
            records = (
                db.query(DistressScore)
                .filter(DistressScore.victim_id == victim_id, DistressScore.timestamp >= cutoff)
                .order_by(DistressScore.timestamp.asc())
                .all()
            )

            if not records or len(records) < 2:
                avg_score = round(records[0].score, 1) if records else 0.0
                return {
                    "window_days": window_days,
                    "direction": "stable",
                    "delta_points": 0.0,
                    "historical_avg": avg_score,
                    "record_count": len(records)
                }

            scores = [r.score for r in records]
            avg_score = round(sum(scores) / float(len(scores)), 1)

            # Split into early half vs recent half to determine trend
            half_point = len(scores) // 2
            early_avg = sum(scores[:half_point]) / float(max(1, half_point))
            recent_avg = sum(scores[half_point:]) / float(max(1, len(scores) - half_point))

            delta = round(recent_avg - early_avg, 1)

            if delta > 5.0:
                direction = "worsening"
            elif delta < -5.0:
                direction = "improving"
            else:
                direction = "stable"

            return {
                "window_days": window_days,
                "direction": direction,
                "delta_points": delta,
                "historical_avg": avg_score,
                "record_count": len(records)
            }
        finally:
            if close_session:
                db.close()

    def calculate_distress_score(
        self,
        nlp_output: Dict[str, Any],
        behavioral_signals: Optional[Dict[str, Any]] = None,
        victim_id: Optional[str] = None,
        save_to_db: bool = True,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        return self.calculate_score(
            nlp_output=nlp_output,
            behavioral_signals=behavioral_signals or {},
            victim_id=victim_id,
            save_to_db=save_to_db,
            db=db
        )

    def calculate_score(
        self,
        nlp_output: Dict[str, Any],
        behavioral_signals: Dict[str, Any],
        victim_id: Optional[str] = None,
        save_to_db: bool = True,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Compute composite distress score, explainability breakdown, and longitudinal trend.
        
        Returns normalized JSON output:
        {
          "distress_score": float (0-100),
          "risk_level": str (Low/Moderate/High/Critical),
          "timestamp": str,
          "trend": dict (7/30/90 day trend analysis),
          "explainability": {
            "method": "Additive Rule-Based Feature Attribution",
            "feature_contributions": [...]
          }
        }
        """
        sub_scores = self._normalize_inputs(nlp_output, behavioral_signals)
        feature_contributions = self._generate_explainability(sub_scores)

        # Compute composite score (0-100)
        total_score = round(sum(c["impact_points"] for c in feature_contributions), 1)
        total_score = max(0.0, min(100.0, total_score))
        risk_level = self._categorize_risk(total_score)
        ts_now = utcnow()

        # Database persistence
        ds_id = None
        if save_to_db and victim_id:
            close_session = False
            if db is None:
                db = SessionLocal()
                close_session = True
            try:
                # Ensure victim exists
                victim = db.query(VictimProfile).filter_by(victim_id=victim_id).first()
                if not victim:
                    victim = VictimProfile(victim_id=victim_id)
                    db.add(victim)
                    db.commit()

                ds_record = DistressScore(
                    victim_id=victim_id,
                    score=total_score,
                    timestamp=ts_now,
                    contributing_factors=sub_scores,
                    model_version="v1.0.0-rule-explainable",
                    confidence=float(nlp_output.get("confidence", 0.90))
                )
                db.add(ds_record)
                db.commit()
                ds_id = ds_record.id
            finally:
                if close_session:
                    db.close()

        # Compute longitudinal trend
        trend_analysis = {}
        if victim_id:
            trend_analysis = self.compute_longitudinal_trend(victim_id=victim_id, window_days=30, db=db)
        else:
            trend_analysis = {
                "window_days": 30,
                "direction": "stable",
                "delta_points": 0.0,
                "historical_avg": total_score,
                "record_count": 1
            }

        return {
            "distress_score_id": ds_id,
            "victim_id": victim_id,
            "distress_score": total_score,
            "risk_level": risk_level,
            "timestamp": ts_now.isoformat(),
            "trend": trend_analysis,
            "explainability": {
                "method": "Additive Rule-Based Feature Attribution",
                "total_score": total_score,
                "feature_contributions": feature_contributions
            }
        }

# Global singleton instance
distress_engine = DynamicDistressEngine()
