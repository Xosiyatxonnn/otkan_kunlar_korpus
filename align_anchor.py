import re, csv, pickle

DASH = '—'

def to_paragraphs(text, lang):
    if lang == 'ru':
        text = text.replace('\xac\n', '').replace('\xad', '')
        text = re.sub(r'([,\.!?;:])([^\s\d])', r'\1 \2', text)
    lines = text.split('\n')
    paras, cur = [], []
    for line in lines:
        s = line.strip()
        if not s:
            if cur: paras.append(' '.join(cur)); cur = []
        else:
            cur.append(s)
    if cur: paras.append(' '.join(cur))
    return paras

def split_sentences(para, lang):
    if lang == 'ru':
        sents = re.split(r'(?<=[.!?])\s+(?=[А-ЯЁ\xab"' + DASH + r'])', para)
    else:
        sents = re.split(r"(?<=[.!?])\s+(?=[A-ZO'‘’\xab" + DASH + r'])', para)
    return [s.strip() for s in sents if len(s.strip()) > 3]

def chapter_to_sentences(text, lang):
    paras = to_paragraphs(text, lang)
    sents = []
    for p in paras:
        sents.extend(split_sentences(p, lang))
    return sents

# ---- Name-cognate anchors (proper nouns / titles transliterated consistently
# across both languages by the translators) used to break long chapters into
# small, re-synchronized windows before running length-based DP. This bounds
# how far a local misalignment can drift before the next shared name resets
# the two sequences back in sync. ----
NAME_PAIRS = [
    ('otabek', 'атабек'),
    ('kumush', 'кумюш'),
    ('hasanali', 'хасанали'),
    ('homid', 'хамид'),
    ('rahmat', 'рахмат'),
    ('yusufbek', 'юсуфбек'),
    ('zaynab', 'зайнаб'),
    ('oftob', 'офтоб'),
    ('ziyo shohichi', 'зия-шахичи'),
    ('musulmonqul', 'мусульманкул'),
    ('azizbek', 'азизбек'),
    ("marg‘ilon", 'маргелан'),
    ('toshkand', 'ташкент'),
    ('o‘zbek oyim', 'узбек-аим'),
    ('usta alim', 'уста алим'),
    ('qutidor', 'кутидор'),
    ('sodiq', 'садык'),
]

def find_events(sents, pairs, side):
    """side: 0 for uz (use pairs[i][0]), 1 for ru (use pairs[i][1])"""
    events = []
    for idx, s in enumerate(sents):
        sl = s.lower()
        for name_id, (uz_n, ru_n) in enumerate(pairs):
            needle = uz_n if side == 0 else ru_n
            if needle in sl:
                events.append((idx, name_id))
    return events

def lcs_anchor_match(uz_events, ru_events):
    """Find a monotonic matching between uz_events and ru_events with equal
    name_id, maximizing count (classic LCS over the name_id sequences),
    return list of (uz_idx, ru_idx) anchor pairs in increasing order."""
    A = [e[1] for e in uz_events]
    B = [e[1] for e in ru_events]
    n, m = len(A), len(B)
    if n == 0 or m == 0:
        return []
    dp = [[0]*(m+1) for _ in range(n+1)]
    for i in range(n-1, -1, -1):
        for j in range(m-1, -1, -1):
            if A[i] == B[j]:
                dp[i][j] = dp[i+1][j+1] + 1
            else:
                dp[i][j] = max(dp[i+1][j], dp[i][j+1])
    pairs = []
    i, j = 0, 0
    while i < n and j < m:
        if A[i] == B[j]:
            pairs.append((uz_events[i][0], ru_events[j][0]))
            i += 1; j += 1
        elif dp[i+1][j] >= dp[i][j+1]:
            i += 1
        else:
            j += 1
    # dedupe: keep only strictly increasing anchors (guard against same
    # sentence matching multiple name_ids producing repeats)
    out = []
    last_i, last_j = -1, -1
    for ui, rj in pairs:
        if ui > last_i and rj > last_j:
            out.append((ui, rj))
            last_i, last_j = ui, rj
    return out

def gale_church(uz, ru):
    n, m = len(uz), len(ru)
    uz_l = [len(s) for s in uz]
    ru_l = [len(s) for s in ru]
    INF = float('inf')
    dp = [[INF]*(m+1) for _ in range(n+1)]
    path = [[None]*(m+1) for _ in range(n+1)]
    dp[0][0] = 0
    def cost(i0,i1,j0,j1):
        a = sum(uz_l[i0:i1]); b = sum(ru_l[j0:j1])
        return abs(1 - a/(b+1))
    for i in range(n+1):
        for j in range(m+1):
            if i==0 and j==0: continue
            opts = []
            if i>=1 and j>=1: opts.append((dp[i-1][j-1]+cost(i-1,i,j-1,j),(i-1,j-1,'1:1')))
            if i>=1 and j>=2: opts.append((dp[i-1][j-2]+cost(i-1,i,j-2,j)+0.1,(i-1,j-2,'1:2')))
            if i>=2 and j>=1: opts.append((dp[i-2][j-1]+cost(i-2,i,j-1,j)+0.1,(i-2,j-1,'2:1')))
            if i>=1: opts.append((dp[i-1][j]+uz_l[i-1]*0.3+1,(i-1,j,'1:0')))
            if j>=1: opts.append((dp[i][j-1]+ru_l[j-1]*0.3+1,(i,j-1,'0:1')))
            if opts:
                best = min(opts, key=lambda x: x[0])
                dp[i][j] = best[0]; path[i][j] = best[1]
    aligned = []
    i, j = n, m
    while i > 0 or j > 0:
        if path[i][j] is None: break
        pi, pj, t = path[i][j]
        aligned.append((' '.join(uz[pi:i]), ' '.join(ru[pj:j]), t))
        i, j = pi, pj
    aligned.reverse()
    return aligned

def anchored_align(uz_sents, ru_sents):
    uz_events = find_events(uz_sents, NAME_PAIRS, 0)
    ru_events = find_events(ru_sents, NAME_PAIRS, 1)
    anchors = lcs_anchor_match(uz_events, ru_events)
    # build window boundaries: (uz_start, uz_end, ru_start, ru_end) inclusive-exclusive
    windows = []
    prev_i, prev_j = 0, 0
    for ai, aj in anchors:
        if ai + 1 > prev_i and aj + 1 > prev_j:
            windows.append((prev_i, ai+1, prev_j, aj+1))
            prev_i, prev_j = ai+1, aj+1
    windows.append((prev_i, len(uz_sents), prev_j, len(ru_sents)))
    # merge degenerate empty windows into neighbors
    merged = []
    for w in windows:
        if w[1] <= w[0] and w[3] <= w[2]:
            continue
        merged.append(list(w))
    # cap any single window from exploding: if a window is too large (>60
    # sentences on either side with no anchor found), just leave it -- DP
    # will still run, just may drift locally within that bounded span.
    all_pairs = []
    for ui0, ui1, rj0, rj1 in merged:
        sub_uz = uz_sents[ui0:ui1]
        sub_ru = ru_sents[rj0:rj1]
        pairs = gale_church(sub_uz, sub_ru)
        all_pairs.extend(pairs)
    return all_pairs, len(anchors), len(merged)

with open('/sessions/charming-happy-johnson/mnt/outputs/align/uz_chapters.pkl','rb') as f:
    uz_chapters = pickle.load(f)
with open('/sessions/charming-happy-johnson/mnt/outputs/align/ru_chapters.pkl','rb') as f:
    ru_chapters = pickle.load(f)

cut = uz_chapters[56].find('\nBitdi')
if cut != -1:
    uz_chapters[56] = uz_chapters[56][:cut].strip()

def part_chap_label(idx):
    if idx < 23: return (1, idx+1)
    elif idx < 40: return (2, idx-23+1)
    else: return (3, idx-40+1)

all_pairs = []
chapter_stats = []
for idx in range(57):
    p, c = part_chap_label(idx)
    uz_sents = chapter_to_sentences(uz_chapters[idx], 'uz')
    ru_sents = chapter_to_sentences(ru_chapters[idx], 'ru')
    pairs, n_anchors, n_windows = anchored_align(uz_sents, ru_sents)
    chapter_stats.append((p, c, len(uz_sents), len(ru_sents), len(pairs), n_anchors, n_windows))
    for u, r, t in pairs:
        all_pairs.append((p, c, u, r, t))
    print(f"Part {p} Ch {c:2d}: UZ={len(uz_sents):4d} RU={len(ru_sents):4d} anchors={n_anchors:3d} windows={n_windows:3d} pairs={len(pairs):4d}")

out_csv = '/sessions/charming-happy-johnson/mnt/outputs/align/parallel_corpus_anchored.csv'
with open(out_csv, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['pair_id','part','chapter','alignment','uzbek','russian'])
    counters = {}
    for p, c, u, r, t in all_pairs:
        key = (p,c)
        counters[key] = counters.get(key, 0) + 1
        pid = f"p{p}_c{c:02d}_{counters[key]:04d}"
        w.writerow([pid, p, c, t, u, r])

with open('/sessions/charming-happy-johnson/mnt/outputs/align/chapter_stats_anchored.pkl', 'wb') as f:
    pickle.dump(chapter_stats, f)

total_pairs = len(all_pairs)
one_to_one = sum(1 for *_, t in all_pairs if t == '1:1')
print(f"\nTOTAL aligned pairs: {total_pairs}")
print(f"1:1 pairs: {one_to_one} ({100*one_to_one/total_pairs:.1f}%)")
type_counts = {}
for *_, t in all_pairs:
    type_counts[t] = type_counts.get(t, 0) + 1
print("Alignment type breakdown:", type_counts)
total_anchors = sum(s[5] for s in chapter_stats)
total_windows = sum(s[6] for s in chapter_stats)
print(f"Total anchors used: {total_anchors}  |  Total windows: {total_windows}  |  avg window size ~{sum(s[2] for s in chapter_stats)/total_windows:.1f} UZ sents")
