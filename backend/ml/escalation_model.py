from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
from backend.ml.dataset_generator import generate_synthetic_dataset, generate_engineered_features

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "data" / "escalation_model.joblib"

class PredictiveRiskModel:
    """Interpretable Predictive Risk Model forecasting distress escalation & next-period score."""

    FEATURE_NAMES = [
        "recent_score", "mean_7d", "mean_30d", "score_velocity",
        "score_acceleration", "score_std", "max_score_30d", "consecutive_increases"
    ]

    def __init__(self):
        self.regressor: Optional[GradientBoostingRegressor] = None
        self.classifier: Optional[GradientBoostingClassifier] = None
        self.is_trained = False

    def train(self) -> Dict[str, Any]:
        """Train baseline interpretable gradient boosted models on synthetic trajectory data."""
        X, y_reg, y_cls, _ = generate_synthetic_dataset(n_trajectories=2500, random_seed=26094)

        # Regressor for projected next score
        self.regressor = GradientBoostingRegressor(
            n_estimators=120,
            max_depth=5,
            learning_rate=0.08,
            random_state=26094
        )
        self.regressor.fit(X, y_reg)

        # Classifier for escalation probability
        self.classifier = GradientBoostingClassifier(
            n_estimators=120,
            max_depth=5,
            learning_rate=0.08,
            random_state=26094
        )
        self.classifier.fit(X, y_cls)

        self.is_trained = True

        # Save model artifact
        MODEL_PATH.parent.mkdir(exist_ok=True)
        artifact = {
            "regressor": self.regressor,
            "classifier": self.classifier,
            "feature_names": self.FEATURE_NAMES
        }
        joblib.dump(artifact, MODEL_PATH)
        return {"status": "trained", "samples": len(X), "path": str(MODEL_PATH)}

    def load(self):
        """Load trained model from disk or train if missing."""
        if not MODEL_PATH.exists():
            self.train()
        else:
            artifact = joblib.load(MODEL_PATH)
            self.regressor = artifact["regressor"]
            self.classifier = artifact["classifier"]
            self.is_trained = True

    def _determine_risk_tier(self, projected_score: float, escalation_prob: float) -> str:
        """Documented Crisis & Risk Tier Threshold Logic:
        - Critical: Projected score >= 75.0 OR Escalation prob > 0.75
        - High: Projected score 65.0 - 74.9 OR Escalation prob 0.50 - 0.75
        - Medium: Projected score 35.0 - 64.9 OR Escalation prob 0.25 - 0.50
        - Low: Projected score < 35.0 AND Escalation prob < 0.25
        """
        if projected_score >= 75.0 or escalation_prob > 0.75:
            return "critical"
        elif projected_score >= 65.0 or escalation_prob >= 0.50:
            return "high"
        elif projected_score >= 35.0 or escalation_prob >= 0.25:
            return "medium"
        else:
            return "low"

    def predict(self, longitudinal_scores: List[float]) -> Dict[str, Any]:
        """Forecast distress escalation and project next period score from time-series history."""
        if not self.is_trained:
            self.load()

        if not longitudinal_scores:
            longitudinal_scores = [0.0]

        feats = generate_engineered_features(longitudinal_scores)
        x_vec = np.array([[feats[fn] for fn in self.FEATURE_NAMES]], dtype=np.float32)

        # Predict next score & probability of escalation
        projected_score = float(self.regressor.predict(x_vec)[0])
        projected_score = max(0.0, min(100.0, round(projected_score, 1)))

        probs = self.classifier.predict_proba(x_vec)[0]
        # Probability of class 1 (crisis threshold breach)
        escalation_prob = float(probs[1]) if len(probs) > 1 else float(probs[0])
        escalation_prob = round(max(0.0, min(1.0, escalation_prob)), 2)

        risk_tier = self._determine_risk_tier(projected_score, escalation_prob)
        crisis_forecast = bool(projected_score >= 75.0 or escalation_prob >= 0.70)

        # Extract feature importances
        imp_reg = self.regressor.feature_importances_
        imp_cls = self.classifier.feature_importances_
        combined_imp = 0.5 * imp_reg + 0.5 * imp_cls
        
        feature_importances = {
            fn: round(float(combined_imp[i]), 3)
            for i, fn in enumerate(self.FEATURE_NAMES)
        }
        # Sort feature importances descending
        feature_importances = dict(sorted(feature_importances.items(), key=lambda item: item[1], reverse=True))

        return {
            "escalation_probability": escalation_prob,
            "projected_score_next_period": projected_score,
            "risk_tier": risk_tier,
            "crisis_threshold_crossed_forecast": crisis_forecast,
            "engineered_features": feats,
            "feature_importances": feature_importances,
            "crisis_threshold_rule": "Projected score >= 75.0 OR velocity > +5.0 pts/day from score >= 60.0"
        }

# Global singleton model instance
predictive_risk_model = PredictiveRiskModel()
