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
    # v2: rely only on terminal-punctuation-triggered splits. An earlier
    # "split at every remaining em-dash" rule over-fired on Uzbek narrative
    # appositives/asides ("X — Y") that aren't sentence boundaries, inflating
    # Uzbek sentence counts ~25-50% relative to Russian and causing alignment
    # drift. Dropping it brought per-chapter UZ:RU sentence-count ratios back
    # toward parity (verified empirically before adopting this version).
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

def gale_church(uz, ru):
    n, m = len(uz), len(ru)
    uz_l = [len(s) for s in uz]
    ru_l = [len(s) for s in ru]
    INF = float('inf')
    dp = [[INF]*(m+1) for _ in range(n+1)]
    path = [[None]*(m+1) for _ in range(n+1)]
    dp[0][0] = 0
    def cost(i0,i1,j0,j1):
        a = sum(uz_l[i0:i1])
        b = sum(ru_l[j0:j1])
        return abs(1 - a/(b+1))
    for i in range(n+1):
        for j in range(m+1):
            if i==0 and j==0: continue
            opts = []
            if i>=1 and j>=1: opts.append((dp[i-1][j-1]+cost(i-1,i,j-1,j),(i-1,j-1,'1:1')))
            if i>=1 and j>=2: opts.append((dp[i-1][j-2]+cost(i-1,i,j-2,j)+0.1,(i-1,j-2,'1:2')))
            if i>=2 and j>=1: opts.append((dp[i-2][j-1]+cost(i-2,i,j-1,j)+0.1,(i-2,j-1,'2:1')))
            if i>=1 and j>=0: opts.append((dp[i-1][j]+uz_l[i-1]*0.3+1,(i-1,j,'1:0')))
            if i>=0 and j>=1: opts.append((dp[i][j-1]+ru_l[j-1]*0.3+1,(i,j-1,'0:1')))
            if opts:
                best = min(opts, key=lambda x: x[0])
                dp[i][j] = best[0]
                path[i][j] = best[1]
    aligned = []
    i, j = n, m
    while i > 0 or j > 0:
        if path[i][j] is None: break
        pi, pj, t = path[i][j]
        aligned.append((' '.join(uz[pi:i]), ' '.join(ru[pj:j]), t))
        i, j = pi, pj
    aligned.reverse()
    return aligned

with open('/sessions/charming-happy-johnson/mnt/outputs/align/uz_chapters.pkl','rb') as f:
    uz_chapters = pickle.load(f)
with open('/sessions/charming-happy-johnson/mnt/outputs/align/ru_chapters.pkl','rb') as f:
    ru_chapters = pickle.load(f)
with open('/sessions/charming-happy-johnson/mnt/outputs/align/chap_meta.pkl','rb') as f:
    meta = pickle.load(f)

uz_titles = meta['uz_titles']  # list of (num, title) length 57, part-relative numbering

# Part 3, Ch 17 (idx 56) ends with the novel's narrative, but the Uzbek
# source also carries a short closing authorial note ("Bitdi" / "THE END" +
# "YOZG'UCHIDAN" / "FROM THE AUTHOR") that has no counterpart in this
# Russian edition (Bygone_days_ru_fixed.txt ends with the narrative only).
# Truncate before "Bitdi" for alignment so this untranslated coda doesn't
# get force-matched against unrelated Russian sentences and drag the
# chapter's alignment off track.
cut = uz_chapters[56].find('\nBitdi')
if cut != -1:
    uz_chapters[56] = uz_chapters[56][:cut].strip()

part_bounds = [23, 17, 17]
def part_chap_label(idx):
    # idx 0..56 -> (part 1-3, chapter num within part)
    if idx < 23: return (1, idx+1)
    elif idx < 40: return (2, idx-23+1)
    else: return (3, idx-40+1)

all_pairs = []
chapter_stats = []
for idx in range(57):
    p, c = part_chap_label(idx)
    uz_sents = chapter_to_sentences(uz_chapters[idx], 'uz')
    ru_sents = chapter_to_sentences(ru_chapters[idx], 'ru')
    pairs = gale_church(uz_sents, ru_sents)
    chapter_stats.append((p, c, len(uz_sents), len(ru_sents), len(pairs)))
    for u, r, t in pairs:
        all_pairs.append((p, c, u, r, t))
    print(f"Part {p} Ch {c:2d}: UZ_sents={len(uz_sents):4d} RU_sents={len(ru_sents):4d} pairs={len(pairs):4d}")

out_csv = '/sessions/charming-happy-johnson/mnt/outputs/align/parallel_corpus_full.csv'
with open(out_csv, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f)
    w.writerow(['pair_id','part','chapter','alignment','uzbek','russian'])
    counters = {}
    for p, c, u, r, t in all_pairs:
        key = (p,c)
        counters[key] = counters.get(key, 0) + 1
        pid = f"p{p}_c{c:02d}_{counters[key]:04d}"
        w.writerow([pid, p, c, t, u, r])

with open('/sessions/charming-happy-johnson/mnt/outputs/align/chapter_stats.pkl', 'wb') as f:
    pickle.dump(chapter_stats, f)

total_pairs = len(all_pairs)
one_to_one = sum(1 for *_, t in all_pairs if t == '1:1')
print(f"\nTOTAL aligned pairs: {total_pairs}")
print(f"1:1 pairs: {one_to_one} ({100*one_to_one/total_pairs:.1f}%)")
type_counts = {}
for *_, t in all_pairs:
    type_counts[t] = type_counts.get(t, 0) + 1
print("Alignment type breakdown:", type_counts)
