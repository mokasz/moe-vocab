import json

with open("data/words.json", "r") as f:
    data = json.load(f)

words = data.get("words", [])

new_words = []
review_words = []

for w in words:
    if not w.get("lastSeen"):
        new_words.append(w)
    else:
        review_words.append(w)

print(f"=== 3/26 単語セット ({len(words)}語) ===")

print(f"\n【復習単語】 ({len(review_words)}語)")
for i, w in enumerate(review_words, 1):
    last_seen = w.get("lastSeen", "")[:10]
    print(f"  {i:2d}. {w['word']:12s} - {w['japanese']} (前回: {last_seen})")

print(f"\n【新規単語】 ({len(new_words)}語)")
for i, w in enumerate(new_words, 1):
    print(f"  {i:2d}. {w['word']:12s} - {w['japanese']}")
