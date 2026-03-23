import json

with open("moe-vocab/data/words.json") as f:
    data = json.load(f)

for w in data["words"]:
    last_seen = w.get("lastSeen", "")
    next_review = w.get("nextReview", "")
    if last_seen: last_seen = last_seen[:10]
    if next_review: next_review = next_review[:10]
    quality = w.get("quality", "New")
    
    reason = ""
    if quality == 0:
        reason = "昨日不正解（Red枠）"
    elif last_seen and next_review and next_review <= "2026-03-23":
        reason = "復習日が来た（Due枠）"
    else:
        reason = "新しい単語（New枠）"
        
    print(f"- {w['word']} (ID: {w['id']}) : {reason} (Last: {last_seen or 'None'}, Next: {next_review or 'None'})")
