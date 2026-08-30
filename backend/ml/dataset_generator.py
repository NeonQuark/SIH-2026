import json
from pathlib import Path
from typing import List, Tuple, Dict, Any
import numpy as np

def generate_engineered_features(scores: List[float]) -> Dict[str, float]:
    """Extract 8 interpretable time-series features from longitudinal DistressScore history."""
    if not scores:
        scores = [0.0]

    recent = float(scores[-1])
    arr = np.array(scores, dtype=float)

    # Moving averages
    mean_7d = float(np.mean(arr[-7:])) if len(arr) >= 1 else recent
    mean_30d = float(np.mean(arr[-30:])) if len(arr) >= 1 else recent

    # Score Velocity (linear regression slope over last 5 entries)
    if len(arr) >= 2:
        window = arr[-5:]
        x = np.arange(len(window))
        # Simple slope calculation
        if len(window) > 1:
            slope = float(np.polyfit(x, window, 1)[0])
        else:
            slope = 0.0
    else:
        slope = 0.0

    # Score Acceleration (change in velocity)
    if len(arr) >= 4:
        first_half_slope = float(arr[-1] - arr[-3]) / 2.0
        second_half_slope = float(arr[-3] - arr[-5 if len(arr) >= 5 else 0]) / 2.0
        acceleration = first_half_slope - second_half_slope
    else:
        acceleration = 0.0

    # Volatility & Peaks
    score_std = float(np.std(arr[-30:])) if len(arr) > 1 else 0.0
    max_30d = float(np.max(arr[-30:]))

    # Consecutive Increases Count
    consecutive = 0
    for i in range(len(arr) - 1, 0, -1):
        if arr[i] > arr[i - 1]:
            consecutive += 1
        else:
            break

    return {
        "recent_score": round(recent, 2),
        "mean_7d": round(mean_7d, 2),
        "mean_30d": round(mean_30d, 2),
        "score_velocity": round(slope, 2),
        "score_acceleration": round(acceleration, 2),
        "score_std": round(score_std, 2),
        "max_score_30d": round(max_30d, 2),
        "consecutive_increases": float(consecutive)
    }


def generate_synthetic_dataset(n_trajectories: int = 1200, random_seed: int = 26094) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[str]]:
    """Generate synthetic victim trajectories (improving, stable, gradual, rapid crisis escalation)."""
    rng = np.random.default_rng(random_seed)
    
    feature_names = [
        "recent_score", "mean_7d", "mean_30d", "score_velocity",
        "score_acceleration", "score_std", "max_score_30d", "consecutive_increases"
    ]

    X_list = []
    y_reg_list = []
    y_cls_list = []

    for _ in range(n_trajectories):
        traj_type = rng.choice(["improving", "stable", "moderate", "gradual_escalation", "rapid_crisis"])
        length = rng.integers(10, 31)

        if traj_type == "improving":
            start = rng.uniform(50, 80)
            end = rng.uniform(10, 30)
            base = np.linspace(start, end, length)
        elif traj_type == "stable":
            level = rng.uniform(15, 35)
            base = np.full(length, level)
        elif traj_type == "moderate":
            level = rng.uniform(40, 60)
            base = np.full(length, level)
        elif traj_type == "gradual_escalation":
            start = rng.uniform(25, 45)
            end = rng.uniform(65, 85)
            base = np.linspace(start, end, length)
        else:  # rapid_crisis
            base = np.linspace(30, 45, max(5, length - 5))
            crisis = np.linspace(45, rng.uniform(80, 98), min(5, length))
            base = np.concatenate([base, crisis])[:length]

        # Add Gaussian noise
        noise = rng.normal(0, 2.5, length)
        trajectory = np.clip(base + noise, 0.0, 100.0)

        # For each time step t >= 5, extract features and predict t+1
        for t in range(5, length - 1):
            sub_history = trajectory[:t+1].tolist()
            feats = generate_engineered_features(sub_history)
            row = [feats[fn] for fn in feature_names]

            next_score = float(trajectory[t+1])

            # Crisis Threshold Logic: next_score >= 75.0 OR velocity > 5.0 starting from >= 60.0
            is_crisis = 1 if (next_score >= 75.0 or (feats["recent_score"] >= 60.0 and feats["score_velocity"] > 5.0)) else 0

            X_list.append(row)
            y_reg_list.append(next_score)
            y_cls_list.append(is_crisis)

    X = np.array(X_list, dtype=np.float32)
    y_reg = np.array(y_reg_list, dtype=np.float32)
    y_cls = np.array(y_cls_list, dtype=np.int32)

    return X, y_reg, y_cls, feature_names


if __name__ == "__main__":
    X, y_reg, y_cls, names = generate_synthetic_dataset()
    print(f"Generated synthetic dataset: X={X.shape}, y_reg={y_reg.shape}, y_cls={y_cls.shape}")
