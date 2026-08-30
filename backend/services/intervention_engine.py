import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.db.session import SessionLocal, ROOT
from backend.db.models import InterventionRecommendation, VictimProfile

RULES_FILE = ROOT / "data" / "intervention_rules_config.json"

class InterventionRecommendationEngine:
    """Hybrid Rule-Based + ML-Assisted Intervention Recommendation Engine."""

    CASE_TYPE_MAP = {
        "rape": "sexual_assault_rape",
        "gang_rape": "sexual_assault_rape",
        "sexual_assault": "sexual_assault_rape",
        "murder": "murder_homicide",
        "homicide": "murder_homicide",
        "witness_intimidation": "witness_intimidation",
        "caste_violence": "caste_violence",
        "land_grab": "land_grab_eviction",
        "eviction": "land_grab_eviction",
        "verbal_abuse": "verbal_abuse_outrage"
    }

    DEFAULT_RULES = {
        "sexual_assault_rape": ["medical", "counselling", "legal_aid", "police_protection", "compensation"],
        "murder_homicide": ["counselling", "witness_protection", "financial_aid", "legal_aid"],
        "witness_intimidation": ["witness_protection", "relocation", "legal_aid"],
        "caste_violence": ["counselling", "relocation", "financial_aid", "rehabilitation"],
        "land_grab_eviction": ["legal_aid", "rehabilitation", "compensation"],
        "verbal_abuse_outrage": ["counselling", "legal_aid"]
    }

    def __init__(self):
        self.rules = self.load_rules()

    def load_rules(self) -> Dict[str, Any]:
        if RULES_FILE.exists():
            try:
                with open(RULES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "rules" in data and isinstance(data["rules"], dict):
                        return data["rules"]
                    if isinstance(data, dict) and len(data) > 0 and "sexual_assault_rape" in data:
                        return data
            except Exception:
                pass
        return dict(self.DEFAULT_RULES)

    def save_rules(self, new_rules: Dict[str, Any]) -> Dict[str, Any]:
        """Update and persist admin-editable rule set."""
        if "rules" in new_rules and isinstance(new_rules["rules"], dict):
            new_rules = new_rules["rules"]
        self.rules = new_rules
        RULES_FILE.parent.mkdir(exist_ok=True)
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(new_rules, f, indent=2)
        return {"status": "updated", "rule_count": len(new_rules)}

    def normalize_case_type(self, raw_case_type: str) -> str:
        key = raw_case_type.lower().strip().replace(" ", "_").replace("-", "_")
        return self.CASE_TYPE_MAP.get(key, key)

    def _compute_ml_feedback_weight(
        self,
        norm_case_type: str,
        intervention_cat: str,
        db: Session
    ) -> float:
        """ML-Assisted feedback scoring: Boosts categories historically acted_upon and penalizes ignored ones."""
        try:
            records = (
                db.query(InterventionRecommendation)
                .filter(
                    InterventionRecommendation.linked_case_id.like(f"%{norm_case_type}%"),
                    InterventionRecommendation.intervention_type == intervention_cat
                )
                .all()
            )

            if not records:
                return 0.0

            acted_count = sum(1 for r in records if r.status in ["acted_upon", "Approved", "Completed"])
            ignored_count = sum(1 for r in records if r.status in ["ignored", "Rejected"])
            total = len(records)

            if total == 0:
                return 0.0

            feedback_boost = (0.30 * (acted_count / total)) - (0.25 * (ignored_count / total))
            return round(feedback_boost, 2)
        except Exception:
            return 0.0

    def get_recommendations(
        self,
        victim_id: str,
        case_type: str,
        risk_profile: Dict[str, Any],
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Generate hybrid rule-based & ML-assisted intervention recommendations for a case."""
        norm_case_type = self.normalize_case_type(case_type)
        risk_tier = risk_profile.get("risk_tier", "medium").lower()

        case_rule = self.rules.get(norm_case_type, {})
        if isinstance(case_rule, list):
            mandatory_cats = case_rule
            risk_dep_cats = []
        elif isinstance(case_rule, dict):
            mandatory_cats = case_rule.get("mandatory", ["counselling", "legal_aid"])
            risk_dep_cats = case_rule.get("risk_dependent", {}).get(risk_tier, [])
        else:
            mandatory_cats = ["counselling", "legal_aid"]
            risk_dep_cats = []

        # Combine categories preserving priority
        all_recommended_cats = []
        for c in mandatory_cats:
            if c not in all_recommended_cats:
                all_recommended_cats.append((c, "Mandatory", 0.90))

        for c in risk_dep_cats:
            if not any(x[0] == c for x in all_recommended_cats):
                all_recommended_cats.append((c, f"Risk_Tier_{risk_tier.capitalize()}", 0.75))

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

            ranked_recommendations = []
            created_records = []

            for cat, priority, base_score in all_recommended_cats:
                ml_boost = self._compute_ml_feedback_weight(norm_case_type, cat, db)
                final_score = round(max(0.10, min(0.99, base_score + ml_boost)), 2)

                details = {
                    "case_type": norm_case_type,
                    "risk_tier": risk_tier,
                    "priority": priority,
                    "base_rule_score": base_score,
                    "ml_feedback_weight": ml_boost
                }

                # Persist in DB
                rec_record = InterventionRecommendation(
                    victim_id=victim_id,
                    linked_case_id=f"CASE-{norm_case_type.upper()}-{victim_id[:8]}",
                    intervention_type=cat,
                    status="Pending",
                    recommendation_details=details
                )
                db.add(rec_record)
                db.flush()
                created_records.append(rec_record)

                ranked_recommendations.append({
                    "recommendation_id": rec_record.id,
                    "intervention_type": cat,
                    "priority": priority,
                    "confidence_score": final_score,
                    "ml_boost": ml_boost,
                    "details": details
                })

            db.commit()

            # Sort descending by confidence score
            ranked_recommendations.sort(key=lambda x: x["confidence_score"], reverse=True)

            return {
                "victim_id": victim_id,
                "case_type": norm_case_type,
                "risk_tier": risk_tier,
                "total_recommendations": len(ranked_recommendations),
                "recommendations": ranked_recommendations
            }
        finally:
            if close_session:
                db.close()

    def log_feedback(
        self,
        recommendation_id: int,
        status: str,
        feedback_notes: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Log officer/counselor feedback (acted_upon vs ignored) for recommendation fine-tuning."""
        valid_statuses = ["acted_upon", "ignored", "in_progress", "completed", "rejected"]
        norm_status = status.lower().strip()
        if norm_status not in valid_statuses:
            return {"status": "error", "reason": f"Invalid feedback status. Must be one of {valid_statuses}"}

        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            rec = db.query(InterventionRecommendation).filter_by(id=recommendation_id).first()
            if not rec:
                return {"status": "error", "reason": f"Recommendation ID {recommendation_id} not found"}

            rec.status = norm_status
            if feedback_notes:
                details = dict(rec.recommendation_details or {})
                details["feedback_notes"] = feedback_notes
                rec.recommendation_details = details

            db.commit()

            return {
                "status": "logged",
                "recommendation_id": rec.id,
                "intervention_type": rec.intervention_type,
                "feedback_status": norm_status,
                "notes": feedback_notes
            }
        finally:
            if close_session:
                db.close()

# Global singleton engine instance
intervention_engine = InterventionRecommendationEngine()
