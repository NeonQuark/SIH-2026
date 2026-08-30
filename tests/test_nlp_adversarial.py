import pytest
from backend.services.nlp_pipeline import nlp_pipeline

ADVERSARIAL_CATEGORIES = {
    "1. Indirect/Understated Distress": [
        "I don't feel safe going out anymore",
        "things have not been okay since the incident",
        "I try not to leave the room when he is around",
        "my hands start shaking every time someone knocks",
        "we have stopped turning the lights on at night"
    ],
    "2. Hinglish Code-Mixed Phrasing": [
        "bahut tension hai yaar, kal koi peecha kar raha tha",
        "bhai raat ko window ke paas aawaaz aati hai, bohot scared hu",
        "sir kal gundey aaye the, bol rahe the case wapas lo",
        "mummy bohot ghabra rahi hai, raste me roka tha unhe",
        "kal raat ko door pe kisi ne zor se knock kiya tha"
    ],
    "3. Sarcasm / Flat Affect Masking Distress": [
        "oh great, another threatening call, just what I needed",
        "wonderful, now they know where I work",
        "amazing, police didn't show up again, feeling super protected",
        "fantastic, my lock was broken when I got home today",
        "lovely, another anonymous letter under my door"
    ],
    "4. Minor / Child-Appropriate Phrasing": [
        "the bad man came near our house again",
        "an uncle told me not to tell anyone or else",
        "I am scared to walk to school alone",
        "he was standing near my playground again today",
        "some people were shouting outside my window and I hid"
    ],
    "5. Formal / Elderly Register Phrasing": [
        "I am writing to inform you I have received threats to my safety",
        "Kindly note that individuals have been observing my residence",
        "Respectfully requesting urgent intervention as I reside alone",
        "The perpetrator approached my premises during evening hours",
        "I am deeply apprehensive about my physical security"
    ],
    "6. Self-Harm / Suicidal Ideation Mentions": [
        "I don't see the point of continuing this fight",
        "I want to end it all, I can't take this harassment anymore",
        "Sometimes I feel everyone would be better off without me",
        "There is no escape from them except dying",
        "I don't want to wake up tomorrow"
    ],
    "7. Explicit Weapon / Violence Mentions": [
        "he showed me a knife and said next time",
        "they came with iron rods and broke the window",
        "he threatened to throw acid on my face",
        "they pointed a gun at my brother and demanded money",
        "he grabbed my neck and threatened to kill me"
    ],
    "8. Non-Distress Control Phrases": [
        "the hearing has been rescheduled to next month",
        "thank you for the update on my application status",
        "I submitted the legal documents to the district office",
        "the counselor session is scheduled for Thursday at 3 PM",
        "please send the receipt for the financial aid claim"
    ]
}

def evaluate_underscored_flag(category: str, sentiment: float, fear: float, anxiety: float) -> str:
    """Diagnostic heuristic to flag under-scored phrases for human sanity check."""
    if "Control" in category:
        if sentiment < -0.3 or fear > 0.35:
            return "FLAG: Over-scored (Control false positive)"
        return "OK (Control)"

    # High severity categories (Weapons, Suicidal, Hinglish, Sarcasm)
    if "Weapon" in category or "Self-Harm" in category:
        if fear < 0.50 and sentiment > -0.7:
            return "FLAG: Under-scored (High violence/self-harm risk missed)"

    if "Sarcasm" in category:
        if sentiment >= 0.0 or fear < 0.40:
            return "FLAG: Under-scored (Sarcasm inverted sentiment)"

    if "Hinglish" in category:
        if fear < 0.45:
            return "FLAG: Under-scored (Hinglish transliteration gap)"

    if "Indirect" in category or "Minor" in category or "Formal" in category:
        if fear < 0.35 and sentiment > -0.4:
            return "FLAG: Under-scored (Subtle distress under-weighted)"

    return "OK (Adequately Scored)"

def run_diagnostic_pass():
    print("\n" + "="*110)
    print("NLP PIPELINE ADVERSARIAL DIAGNOSTIC TEST REPORT")
    print("="*110 + "\n")

    results = []

    for cat, phrases in ADVERSARIAL_CATEGORIES.items():
        print(f"\n--- Category: {cat} ---")
        for phrase in phrases:
            res = nlp_pipeline.analyze_text(phrase)
            sentiment = res.get("sentiment_score", 0.0)
            emotions = res.get("emotion_labels", {})
            fear = emotions.get("fear", 0.0)
            anxiety = emotions.get("anxiety", 0.0)
            anger = emotions.get("anger", 0.0)
            confidence = res.get("confidence", 0.0)

            flag = evaluate_underscored_flag(cat, sentiment, fear, anxiety)

            results.append({
                "category": cat,
                "phrase": phrase,
                "sentiment": sentiment,
                "fear": fear,
                "anxiety": anxiety,
                "anger": anger,
                "confidence": confidence,
                "flag": flag
            })

            print(f"[{flag}] | Text: \"{phrase}\"")
            print(f"   -> Sent: {sentiment} | Fear: {fear} | Anx: {anxiety} | Ang: {anger} | Conf: {confidence}\n")

    return results

def test_nlp_adversarial_suite():
    results = run_diagnostic_pass()
    assert len(results) == 40
