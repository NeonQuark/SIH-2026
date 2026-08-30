from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from backend.db.session import SessionLocal
from backend.db.models import VictimProfile, InteractionLog, DistressScore, RiskAlert, InterventionRecommendation

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class DashboardAnalyticsService:
    """Role-Scoped Dashboard Analytics Service (District / State / National) with Zero Plaintext PII."""

    def _get_scoped_victim_ids(
        self,
        db: Session,
        role: str,
        district: Optional[str] = None,
        state: Optional[str] = None
    ) -> List[str]:
        """Fetch victim_ids permitted for the given user role and jurisdiction."""
        query = db.query(VictimProfile.victim_id)
        role_norm = role.lower().strip()

        if role_norm == "district_officer" and district:
            query = query.filter(VictimProfile.district == district)
        elif role_norm == "state_officer" and state:
            query = query.filter(VictimProfile.state == state)

        return [r[0] for r in query.all()]

    def get_dashboard_metrics(
        self,
        role: str = "national_officer",
        district: Optional[str] = None,
        state: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Fetch role-scoped aggregate distress trends, SLA response metrics, and intervention stats."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            allowed_victim_ids = self._get_scoped_victim_ids(db, role, district, state)

            # 1. Aggregate Distress Trends over Time (Daily Averages)
            ds_query = db.query(
                func.strftime('%Y-%m-%d', DistressScore.timestamp).label("date"),
                func.avg(DistressScore.score).label("avg_score"),
                func.count(DistressScore.id).label("count")
            )
            if allowed_victim_ids:
                ds_query = ds_query.filter(DistressScore.victim_id.in_(allowed_victim_ids))

            trend_rows = ds_query.group_by("date").order_by("date").all()
            distress_trends = [
                {"date": row.date, "avg_distress_score": round(row.avg_score, 1), "checkin_count": row.count}
                for row in trend_rows
            ]

            # 2. Alert Response SLA Metrics
            alert_query = db.query(RiskAlert)
            if allowed_victim_ids:
                alert_query = alert_query.filter(RiskAlert.victim_id.in_(allowed_victim_ids))

            alerts = alert_query.all()
            total_alerts = len(alerts)
            in_sla_count = sum(1 for a in alerts if a.sla_status == "IN_SLA")
            breached_count = sum(1 for a in alerts if a.sla_status == "BREACHED")
            acknowledged_count = sum(1 for a in alerts if a.status == "ACKNOWLEDGED")

            sla_compliance_pct = round((in_sla_count / total_alerts * 100), 1) if total_alerts > 0 else 100.0

            sla_metrics = {
                "total_alerts": total_alerts,
                "in_sla_count": in_sla_count,
                "breached_count": breached_count,
                "acknowledged_count": acknowledged_count,
                "sla_compliance_rate_pct": sla_compliance_pct
            }

            # 3. Intervention Effectiveness Stats
            interv_query = db.query(InterventionRecommendation)
            if allowed_victim_ids:
                interv_query = interv_query.filter(InterventionRecommendation.victim_id.in_(allowed_victim_ids))

            interventions = interv_query.all()
            total_interventions = len(interventions)
            acted_upon_count = sum(1 for i in interventions if i.status in ["acted_upon", "Approved", "Completed"])
            ignored_count = sum(1 for i in interventions if i.status in ["ignored", "Rejected"])
            pending_count = sum(1 for i in interventions if i.status == "Pending")

            eval_count = acted_upon_count + ignored_count
            acceptance_rate_pct = round((acted_upon_count / eval_count * 100), 1) if eval_count > 0 else 0.0

            category_breakdown = {}
            for i in interventions:
                cat = i.intervention_type
                category_breakdown[cat] = category_breakdown.get(cat, 0) + 1

            intervention_stats = {
                "total_recommended": total_interventions,
                "acted_upon_count": acted_upon_count,
                "ignored_count": ignored_count,
                "pending_count": pending_count,
                "acceptance_rate_pct": acceptance_rate_pct,
                "category_breakdown": category_breakdown
            }

            return {
                "jurisdiction_scope": {
                    "role": role,
                    "district": district if role.lower() == "district_officer" else None,
                    "state": state if role.lower() == "state_officer" else None,
                    "scoped_victim_count": len(allowed_victim_ids)
                },
                "distress_trends": distress_trends,
                "sla_metrics": sla_metrics,
                "intervention_stats": intervention_stats
            }
        finally:
            if close_session:
                db.close()

    def get_high_risk_cases(
        self,
        role: str = "national_officer",
        district: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 50,
        db: Optional[Session] = None
    ) -> List[Dict[str, Any]]:
        """Fetch list of high-risk cases filtered by role scope (Zero Plaintext PII)."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            allowed_victim_ids = self._get_scoped_victim_ids(db, role, district, state)

            query = db.query(VictimProfile)
            if allowed_victim_ids:
                query = query.filter(VictimProfile.victim_id.in_(allowed_victim_ids))

            victims = query.all()
            results = []

            for v in victims:
                # Latest distress score
                latest_ds = (
                    db.query(DistressScore)
                    .filter_by(victim_id=v.victim_id)
                    .order_by(DistressScore.timestamp.desc())
                    .first()
                )
                score_val = latest_ds.score if latest_ds else 0.0

                # Active alert
                active_alert = (
                    db.query(RiskAlert)
                    .filter_by(victim_id=v.victim_id, status="Open")
                    .order_by(RiskAlert.created_at.desc())
                    .first()
                )

                if score_val >= 50.0 or active_alert is not None:
                    risk_tier = "critical" if score_val >= 75.0 else ("high" if score_val >= 65.0 else "medium")
                    results.append({
                        "victim_id": v.victim_id,  # Pseudonymized join key
                        "district": v.district or "Unassigned",
                        "state": v.state or "Unassigned",
                        "latest_distress_score": score_val,
                        "risk_tier": risk_tier,
                        "active_alert_id": active_alert.id if active_alert else None,
                        "assigned_officer": active_alert.assigned_officer_or_counsellor if active_alert else None,
                        "created_at": v.created_at.isoformat() if v.created_at else None
                    })

            # Sort descending by score
            results.sort(key=lambda x: x["latest_distress_score"], reverse=True)
            return results[:limit]
        finally:
            if close_session:
                db.close()

    def get_case_timeline(
        self,
        victim_id: str,
        role: str = "national_officer",
        district: Optional[str] = None,
        state: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Fetch pseudonymized individual case timeline for drill-down view."""
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True

        try:
            victim = db.query(VictimProfile).filter_by(victim_id=victim_id).first()
            if not victim:
                return {"status": "error", "reason": f"Victim ID {victim_id} not found"}

            # RBAC Scope Authorization Check
            role_norm = role.lower().strip()
            if role_norm == "district_officer" and district and victim.district != district:
                return {"status": "error", "reason": f"Unauthorized access to victim outside assigned district '{district}'"}
            if role_norm == "state_officer" and state and victim.state != state:
                return {"status": "error", "reason": f"Unauthorized access to victim outside assigned state '{state}'"}

            # Aggregate Timeline Events
            events = []

            # 1. Interaction Logs
            logs = db.query(InteractionLog).filter_by(victim_id=victim_id).all()
            for l in logs:
                events.append({
                    "event_type": "interaction",
                    "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                    "channel": l.channel,
                    "raw_sentiment_score": l.raw_sentiment_score,
                    "raw_emotion_scores": l.raw_emotion_scores
                })

            # 2. Distress Scores
            scores = db.query(DistressScore).filter_by(victim_id=victim_id).all()
            for s in scores:
                events.append({
                    "event_type": "distress_score",
                    "timestamp": s.timestamp.isoformat() if s.timestamp else None,
                    "score": s.score,
                    "contributing_factors": s.contributing_factors
                })

            # 3. Risk Alerts
            alerts = db.query(RiskAlert).filter_by(victim_id=victim_id).all()
            for a in alerts:
                events.append({
                    "event_type": "risk_alert",
                    "timestamp": a.created_at.isoformat() if a.created_at else None,
                    "trigger_reason": a.trigger_reason,
                    "jurisdiction_level": a.jurisdiction_level,
                    "status": a.status,
                    "sla_status": a.sla_status
                })

            # 4. Intervention Recommendations
            interventions = db.query(InterventionRecommendation).filter_by(victim_id=victim_id).all()
            for i in interventions:
                events.append({
                    "event_type": "intervention",
                    "timestamp": i.created_at.isoformat() if i.created_at else None,
                    "intervention_type": i.intervention_type,
                    "status": i.status,
                    "recommendation_details": i.recommendation_details
                })

            # Sort timeline events chronologically
            events.sort(key=lambda x: x["timestamp"] or "")

            return {
                "victim_id": victim_id,  # Pseudonymized UUID
                "district": victim.district,
                "state": victim.state,
                "total_events": len(events),
                "timeline": events
            }
        finally:
            if close_session:
                db.close()

# Global singleton dashboard analytics service instance
dashboard_service = DashboardAnalyticsService()
