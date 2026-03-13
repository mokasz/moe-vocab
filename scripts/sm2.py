# kaya-vocab/scripts/sm2.py

MASTERED_INTERVAL = 21  # この日数以上で習得済み

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
        interval = 1
    elif repetitions == 2:
        interval = 6
    else:
        interval = round(interval * ease)
    return ease, interval, repetitions


def quality_from_status(status: str) -> int:
    """progress_sync の status を SM-2 quality 値に変換"""
    return {'green': 4, 'yellow': 2, 'red': 0}.get(status, 0)


def is_mastered(interval: int) -> bool:
    """interval が閾値以上なら習得済み"""
    return interval >= MASTERED_INTERVAL
