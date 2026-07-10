import re, csv, sys

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
        # This RU source uses a plain ASCII hyphen '-' (not em-dash) to
        # mark dialogue turns, e.g. "...задумчивости. - В любое удобное..."
        # Without '-' in the lookahead, runs of consecutive dialogue lines
        # joined into one paragraph collapse into a single giant
        # "sentence" (observed: 5 distinct utterances merged into one),
        # which starves later alignment windows of RU sentences and causes
        # a cascade of spurious 1:0 (Uzbek-only) pairs at the end.
        sents = re.split(r'(?<=[.!?])\s+(?=[А-ЯЁ\xab"\-' + DASH + r'])', para)
    else:
        sents = re.split(r"(?<=[.!?])\s+(?=[A-ZO'‘’\xab" + DASH + r'])', para)
    return [s.strip() for s in sents if len(s.strip()) > 3]

def chapter_to_sentences(text, lang):
    paras = to_paragraphs(text, lang)
    sents = []
    for p in paras:
        sents.extend(split_sentences(p, lang))
    return sents

NAME_PAIRS = [
    ('otabek', 'атабек'),
    ('kumush', 'кумюш'),
    ('hasanali', 'хасанали'),
    ('homid', 'хамид'),
    ('rahmat', 'рахмат'),
    ('yusufbe', 'юсуфбек'),   # 'yusufbe' matches both 'yusufbek' and truncated 'yusufbe'
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
    ('mirzakarim', 'мирзакарим'),
    ('gulsin', 'гульсун'),
    ('xonimbibi', 'ханым'),
    ('anorgul', 'анаргул'),
    ('savra', 'савра'),
    ("qo’rboshi", 'курбаши'),
    # Added for p2 ch3: truncated 'yusufbe' form (already handled above);
    # 'devona/дивана' provides dense anchors for this chapter.
    ('devona', 'дивана'),
    ('karimqul', 'каримкул'),
]
def find_events(sents, pairs, side):
    events = []
    for idx, s in enumerate(sents):
        sl = s.lower()
        for name_id, (uz_n, ru_n) in enumerate(pairs):
            needle = uz_n if side == 0 else ru_n
            if needle in sl:
                events.append((idx, name_id))
    return events

def lcs_anchor_match(uz_events, ru_events):
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
            # 1:3/3:1: handles a pattern where Qodiriy writes one long,
            # clause-heavy descriptive/dialogue sentence that RU renders as
            # 3+ short sentences (observed in ch16's physical-description and
            # battle-report passages). Without this, the extra RU (or UZ)
            # pieces become orphaned 0:1/1:0 rows even though the content is
            # genuinely paired -- just at a ratio the old 1:2/2:1 cap
            # couldn't express. Higher penalty (+0.2) keeps it a last resort.
            if i>=1 and j>=3: opts.append((dp[i-1][j-3]+cost(i-1,i,j-3,j)+0.2,(i-1,j-3,'1:3')))
            if i>=3 and j>=1: opts.append((dp[i-3][j-1]+cost(i-3,i,j-1,j)+0.2,(i-3,j-1,'3:1')))
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
    windows = []
    prev_i, prev_j = 0, 0
    for ai, aj in anchors:
        if ai + 1 > prev_i and aj + 1 > prev_j:
            windows.append((prev_i, ai+1, prev_j, aj+1))
            prev_i, prev_j = ai+1, aj+1
    windows.append((prev_i, len(uz_sents), prev_j, len(ru_sents)))
    merged = [list(w) for w in windows if not (w[1] <= w[0] and w[3] <= w[2])]
    all_pairs = []
    for ui0, ui1, rj0, rj1 in merged:
        sub_uz = uz_sents[ui0:ui1]
        sub_ru = ru_sents[rj0:rj1]
        pairs = gale_church(sub_uz, sub_ru)
        all_pairs.extend(pairs)
    return all_pairs, len(anchors), len(merged)

def strip_title(text):
    # Strip a leading UTF-8 BOM if present -- uploaded chapter .txt files
    # have one, and it silently broke the old version of this function
    # (re.match against "﻿1. ..." doesn't match "^\d+", so the title
    # line fell through unstripped, then got mangled by the sentence
    # splitter into a bogus extra "sentence").
    text = text.lstrip('﻿')
    lines = text.split('\n')
    for i, l in enumerate(lines):
        s = l.strip()
        if not s:
            continue  # skip leading blank lines, keep looking for the title
        if re.match(r'^\d+\.\s+\S', s):
            return '\n'.join(lines[i+1:])
        return text
    return text

if __name__ == '__main__':
    uz_path, ru_path, out_csv, pid_prefix = sys.argv[1:5]
    with open(uz_path, encoding='utf-8') as f:
        uz_text = f.read()
    with open(ru_path, encoding='utf-8') as f:
        ru_text = f.read()

    uz_text = strip_title(uz_text)
    ru_text = strip_title(ru_text)

    uz_sents = chapter_to_sentences(uz_text, 'uz')
    ru_sents = chapter_to_sentences(ru_text, 'ru')
    pairs, n_anchors, n_windows = anchored_align(uz_sents, ru_sents)

    print(f"UZ sentences: {len(uz_sents)}  RU sentences: {len(ru_sents)}")
    print(f"Anchors matched: {n_anchors}  Windows: {n_windows}  Pairs: {len(pairs)}")
    type_counts = {}
    for *_, t in pairs:
        type_counts[t] = type_counts.get(t, 0) + 1
    print("Type breakdown:", type_counts)

    with open(out_csv, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['pair_id','alignment','uzbek','russian'])
        for idx, (u, r, t) in enumerate(pairs, 1):
            w.writerow([f'{pid_prefix}_{idx:04d}', t, u, r])

    print(f"\nWritten to {out_csv}")
