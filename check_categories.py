import json

with open("data/words.json", "r") as f:
    words_data = json.load(f)
    words = words_data["words"]
    passage = words_data.get("passage", {})

new_words = []
due_words = []
red_words = []

for w in words:
    next_review = w.get("nextReview")
    interval = w.get("interval", 1)
    
    if next_review is None:
        new_words.append(w)
    else:
        # Assuming interval=1 means it was likely marked "red" or recently reset.
        if interval == 1:
            red_words.append(w)
        else:
            due_words.append(w)

print(f"Total Words for {words_data['meta']['created']}: {len(words)}")
print(f"Theme: {passage.get('theme', 'None')}")
print(f"Version: {words_data['meta']['version']}")
print("-" * 30)

print(f"🆕 New Words (新規): {len(new_words)}")
for w in new_words:
    print(f"  [{w['id']}] {w['word']} (Section {w['section']})")

print(f"\n❌ Review Words (要注意/前回の不正解など - Interval 1): {len(red_words)}")
for w in red_words[:10]: # limit to 10 for brevity if many
    print(f"  [{w['id']}] {w['word']} (Next Review: {w['nextReview']})")
if len(red_words) > 10: print(f"  ... and {len(red_words)-10} more.")

print(f"\n✅ Review Words (通常の復習 - Interval > 1): {len(due_words)}")
for w in due_words[:10]:
    print(f"  [{w['id']}] {w['word']} (Interval: {w['interval']} days, Next Review: {w['nextReview']})")
if len(due_words) > 10: print(f"  ... and {len(due_words)-10} more.")
