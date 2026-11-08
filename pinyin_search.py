"""Cached, offline pinyin aliases for shortcut names."""
import sys, re
from functools import lru_cache
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
from pypinyin import lazy_pinyin, Style

def compact(text):
    return re.sub(r"[\s_’'\-]+", '', text.casefold())

@lru_cache(maxsize=2048)
def aliases(name):
    if not re.search(r'[\u3400-\u9fff]', name): return '', ''
    full = ''.join(lazy_pinyin(name, style=Style.NORMAL))
    initials = ''.join(lazy_pinyin(name, style=Style.FIRST_LETTER))
    return compact(full), compact(initials)

def pinyin_score(name, query):
    q = compact(query)
    if not q or not re.fullmatch(r'[a-z0-9]+', q): return 0
    full, initials = aliases(name)
    best = 0
    for alias, exact, prefix, contains in ((full, 100, 65, 40), (initials, 85, 55, 30)):
        if alias:
            best = max(best, exact if q == alias else prefix if alias.startswith(q) else contains if q in alias else 0)
    return best
