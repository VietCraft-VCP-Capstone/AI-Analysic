import math
from collections import Counter, defaultdict

from .normalize import ngrams


def lift_table(titles, groups, top, min_count=20, alpha=1.0):
    rows = defaultdict(list)
    for title, group, is_top in zip(titles, groups, top, strict=True):
        if group is not None:
            rows[group].append((set(ngrams(title)), bool(is_top)))
    table = {}
    for group, docs in rows.items():
        c_all, c_top = Counter(), Counter()
        for terms, is_top in docs:
            c_all.update(terms)
            if is_top:
                c_top.update(terms)
        kept = [t for t, count in c_all.items() if count >= min_count]
        v = len(kept)
        n_all = sum(c_all[t] for t in kept)
        n_top = sum(c_top[t] for t in kept)
        table[group] = {
            term: math.log(
                ((c_top[term] + alpha) / (n_top + alpha * v))
                / ((c_all[term] + alpha) / (n_all + alpha * v))
            )
            for term in kept
        }
    return table
