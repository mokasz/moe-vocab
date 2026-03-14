import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from generate_words import select_words, load_progress, MEDICAL_THEMES, DUE_MAX, DAILY_LIMIT
from sm2 import sm2_update

def make_word(word_id, status="new", interval=1, last_seen=None):
    return {
        "id": word_id, "word": f"w{word_id}", "pos": "noun",
        "part": 3 if word_id > 1500 else 2 if word_id > 800 else 1,
        "section": (word_id - 1) // 100 + 1,
        "japanese": f"意味{word_id}", "sentence": "Ex.", "sentence_ja": "例。",
        "status": status, "ease": 2.5, "interval": interval,
        "repetitions": 0, "lastSeen": last_seen,
    }

def make_due(word_id):
    """期限到来済みの green 単語（昨日学習・interval=1）"""
    return make_word(word_id, status="green", interval=1, last_seen="2026-03-13")

# ── select_words: red ≥ 1 のとき（現行仕様） ────────────────────────────────

def test_select_words_prioritizes_red():
    words = [make_word(i) for i in range(1, 50)]
    words[0]["status"] = "red"
    selected = select_words(words, daily_limit=10)
    assert any(w["id"] == 1 for w in selected)

def test_select_words_part_descending_for_new():
    """新単語は part 降順で選ぶ（Part3 > Part2 > Part1）"""
    part1 = [make_word(i) for i in range(1, 101)]      # part=1, section=1
    part3 = [make_word(i) for i in range(1801, 1901)]  # part=3, section=19
    selected = select_words(part1 + part3, daily_limit=10)
    assert all(w["part"] == 3 for w in selected)

def test_select_words_section_ascending_within_part():
    """同じ part 内では section 昇順（section16 → 17 → 18 → 19）"""
    # Part3: section16(id=1501-1510), section19(id=1801-1810) を混在
    sec16 = [make_word(i) for i in range(1501, 1511)]  # part=3, section=16
    sec19 = [make_word(i) for i in range(1801, 1811)]  # part=3, section=19
    selected = select_words(sec16 + sec19, daily_limit=10)
    assert all(w["section"] == 16 for w in selected)

def test_select_words_respects_limit():
    words = [make_word(i) for i in range(1, 1901)]
    assert len(select_words(words, daily_limit=30)) <= 30

def test_red_nonzero_due_not_capped():
    """red ≥ 1 のとき due は DUE_MAX で打ち切られない（現行仕様）"""
    red = [make_word(1, status="red")]
    due = [make_due(i) for i in range(2, 22)]   # 20語
    new = [make_word(i) for i in range(100, 200)]
    selected = select_words(red + due + new, daily_limit=30)
    due_ids = {w["id"] for w in selected if w["status"] == "green"}
    assert len(due_ids) == 20  # due が DUE_MAX=15 で打ち切られていないこと

def test_red_nonzero_total_respects_limit():
    """red ≥ 1 のとき合計は daily_limit を超えない"""
    red = [make_word(i, status="red") for i in range(1, 11)]    # 10語
    due = [make_due(i) for i in range(100, 120)]                 # 20語
    new = [make_word(i) for i in range(200, 300)]
    selected = select_words(red + due + new, daily_limit=30)
    assert len(selected) == 30

# ── select_words: red = 0 のとき（新仕様） ──────────────────────────────────

def test_red_zero_due_capped_at_due_max():
    """red=0, due=20 → due は DUE_MAX=15 語に制限される"""
    due = [make_due(i) for i in range(1, 21)]    # 20語
    new = [make_word(i) for i in range(100, 200)]
    selected = select_words(due + new, daily_limit=30)
    due_selected = [w for w in selected if w["status"] == "green"]
    assert len(due_selected) == DUE_MAX

def test_red_zero_new_fills_remaining():
    """red=0, due=15 → new が残り15語を埋めて合計30語"""
    due = [make_due(i) for i in range(1, 16)]    # 15語
    new = [make_word(i) for i in range(100, 200)]
    selected = select_words(due + new, daily_limit=30)
    assert len(selected) == 30
    new_selected = [w for w in selected if w["status"] == "new"]
    assert len(new_selected) == DAILY_LIMIT - DUE_MAX

def test_red_zero_due_sparse_new_fills_more():
    """red=0, due=5 → due=5, new=25, 合計30"""
    due = [make_due(i) for i in range(1, 6)]     # 5語
    new = [make_word(i) for i in range(100, 200)]
    selected = select_words(due + new, daily_limit=30)
    assert len(selected) == 30
    due_selected = [w for w in selected if w["status"] == "green"]
    new_selected = [w for w in selected if w["status"] == "new"]
    assert len(due_selected) == 5
    assert len(new_selected) == 25

def test_red_zero_due_zero_all_new():
    """red=0, due=0 → new のみ30語"""
    new = [make_word(i) for i in range(1, 50)]
    selected = select_words(new, daily_limit=30)
    assert len(selected) == 30
    assert all(w["status"] == "new" for w in selected)

# ── SM-2: interval 設定 ──────────────────────────────────────────────────────

def test_sm2_first_correct_interval_is_3():
    """1回目正解（repetitions: 0→1）→ interval=3"""
    _, interval, repetitions = sm2_update(ease=2.5, interval=1, repetitions=0, quality=4)
    assert repetitions == 1
    assert interval == 3

def test_sm2_second_correct_interval_is_6():
    """2回目正解（repetitions: 1→2）→ interval=6（変更なし）"""
    _, interval, repetitions = sm2_update(ease=2.5, interval=3, repetitions=1, quality=4)
    assert repetitions == 2
    assert interval == 6

def test_sm2_incorrect_resets():
    """不正解 → interval=1, repetitions=0 にリセット"""
    _, interval, repetitions = sm2_update(ease=2.5, interval=3, repetitions=1, quality=0)
    assert interval == 1
    assert repetitions == 0

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
                "ease_factor": 1.3,
                "interval_days": 0,
                "repetitions": 0,
                "last_studied": None,
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
