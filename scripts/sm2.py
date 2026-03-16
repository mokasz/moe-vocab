# moe-vocab/scripts/sm2.py

def sm2_update(ease: float, interval: int, repetitions: int, quality: int):
    """
    SM-2 アルゴリズム。
    quality: 4=正解ヒントなし, 2=正解ヒントあり, 0=不正解
    returns: (ease, interval, repetitions)
    """
    if quality < 2:  # 不正解 → リセット
        return ease, 1, 0

    ease = max(1.3, ease + 0.1 - (4 - quality) * 0.08)
    repetitions += 1
    if repetitions == 1:
        interval = 3
    elif repetitions == 2:
        interval = 6
    else:
        interval = round(interval * ease)
    return ease, interval, repetitions


def quality_from_review_log(ratings: list[int]) -> int:
    """
    当日の review_log の rating リストから SM-2 quality を決定する。
    rating: green=4, red=1（moe-vocab は yellow なし）
    - red が1件でもある → 0
    - 全部 green → 4
    - 記録なし → 0（フォールバック）
    """
    if not ratings:
        return 0
    if 1 in ratings:
        return 0
    return 4
