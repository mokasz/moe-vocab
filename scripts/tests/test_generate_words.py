import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from generate_words import select_words, load_progress, MEDICAL_THEMES

def make_word(word_id, status="new", interval=1):
    return {
        "id": word_id, "word": f"w{word_id}", "pos": "noun",
        "part": 3 if word_id > 1500 else 2 if word_id > 800 else 1,
        "section": (word_id - 1) // 100 + 1,
        "japanese": f"意味{word_id}", "sentence": "Ex.", "sentence_ja": "例。",
        "status": status, "ease": 2.5, "interval": interval,
        "repetitions": 0, "lastSeen": None,
    }

def test_select_words_prioritizes_red():
    words = [make_word(i) for i in range(1, 50)]
    words[0]["status"] = "red"
    selected = select_words(words, daily_limit=10)
    assert any(w["id"] == 1 for w in selected)

def test_select_words_reverse_section_for_new():
    low = [make_word(i) for i in range(1, 101)]   # section 1
    high = [make_word(i) for i in range(1801, 1901)]  # section 19
    selected = select_words(low + high, daily_limit=10)
    assert all(w["id"] >= 1801 for w in selected)

def test_select_words_respects_limit():
    words = [make_word(i) for i in range(1, 1901)]
    assert len(select_words(words, daily_limit=30)) <= 30

def test_medical_themes_not_empty():
    assert len(MEDICAL_THEMES) >= 5
    assert all(isinstance(t, str) for t in MEDICAL_THEMES)


def test_load_progress_preserves_zero_values():
    """load_progress must not replace zero sm2_interval/repetitions with defaults."""
    # Build a minimal word list
    words = [make_word(42)]

    # Simulate a Supabase row where interval=0 and repetitions=0
    class FakeQuery:
        data = [
            {
                "word_key": "42",
                "status": "red",
                "sm2_ease": 1.3,
                "sm2_interval": 0,
                "sm2_repetitions": 0,
                "last_seen": None,
            }
        ]

    class FakeTable:
        def select(self, *a): return self
        def eq(self, *a): return self
        def execute(self): return FakeQuery()

    class FakeSb:
        def table(self, name): return FakeTable()

    result = load_progress(FakeSb(), words)
    w = result[0]
    assert w["interval"] == 0, f"interval should be 0, got {w['interval']}"
    assert w["repetitions"] == 0, f"repetitions should be 0, got {w['repetitions']}"
    assert w["ease"] == 1.3, f"ease should be 1.3, got {w['ease']}"
    assert w["status"] == "red"
