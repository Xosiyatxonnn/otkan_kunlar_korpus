# O'tkan Kunlar / Минувшие Дни — Uzbek–Russian Parallel Corpus Alignment
 
Sentence-alignment scripts for building a parallel corpus of Abdulla Qodiriy's novel
*O'tkan Kunlar* (Uzbek, 1925) and its Russian translation *Минувшие Дни* (*Bygone Days*).
The corpus covers all three parts of the novel (57 chapters, ~9 000 sentence pairs).
 
---
 
## Files
 
| File | Purpose |
|------|---------|
| `align_single_chapter.py` | **Main script.** Aligns one chapter at a time from two plain-text files. Used for all Part 3 chapters. |
| `align_anchor.py` | Batch script for Parts 1–2. Reads pre-split chapter texts from pickled lists, runs the same anchor-based alignment over all 57 chapters, writes a single corpus CSV. |
| `align_full.py` | Baseline Gale-Church (no anchor windowing). Used for early development and comparison against the anchor version. |
 
Only `align_single_chapter.py` is needed to reproduce Part 3 alignments from scratch.
`align_anchor.py` and `align_full.py` depend on pre-split `.pkl` files not included here.
 
---
 
## Usage
 
```bash
python align_single_chapter.py uz_chapter.txt ru_chapter.txt output.csv PREFIX
```
 
**Arguments**
 
| Argument | Description |
|----------|-------------|
| `uz_chapter.txt` | Uzbek chapter text (UTF-8, chapter heading on first non-blank line) |
| `ru_chapter.txt` | Russian chapter text (UTF-8, same convention) |
| `output.csv` | Path for the output CSV |
| `PREFIX` | Pair-ID prefix, e.g. `p3_ch5` → IDs like `p3_ch5_0001` |
 
**Example**
 
```bash
python align_single_chapter.py p3_ch5_uz.txt p3_ch5_ru.txt p3_ch5_aligned.csv p3_ch5
```
 
**Output columns:** `pair_id`, `alignment`, `uzbek`, `russian`
 
**Alignment types:** `1:1`, `1:2`, `2:1`, `1:3`, `3:1`, `1:0` (UZ-only), `0:1` (RU-only)
 
**Requirements:** Python 3.6+, standard library only (no external packages).
 
---
 
## How It Works
 
### 1. Sentence tokenisation
 
Text is first split into paragraphs on blank lines, then sentences within each paragraph
are split on terminal punctuation (`[.!?]`) followed by an uppercase letter or opening
quote. Two language-specific adjustments are made:
 
- **Russian:** OCR artefacts (soft hyphen `\xad`, non-breaking space before newline `\xac\n`)
  are stripped. An ASCII hyphen used as a dialogue-turn marker (`- Speech...`) is included
  in the sentence-boundary lookahead so consecutive dialogue lines do not collapse into
  one giant "sentence".
- **Uzbek:** Apostrophe variants used in Uzbek orthography (`'`, `'`, `ʼ`) are included
  in the lookahead to avoid false splits inside possessives and loan words.
Both tokenisers discard tokens shorter than 4 characters.
 
### 2. Anchor-based windowing
 
Proper nouns (character names, place names) that are transliterated consistently across
both languages are used as synchronisation anchors. The 25 bilingual pairs in `NAME_PAIRS`
are substring-matched against every sentence in each language. The resulting
*(sentence\_index, name\_id)* event sequences are aligned with LCS to find a monotonic
set of shared anchor points. These anchors partition the chapter into small, independent
windows. Gale-Church DP runs separately per window, so a local misalignment cannot
propagate past the next anchor.
 
**Current anchor pairs** (Uzbek → Russian):
 
| Uzbek | Russian |
|-------|---------|
| otabek | атабек |
| kumush | кумюш |
| hasanali | хасанали |
| homid | хамид |
| rahmat | рахмат |
| yusufbe | юсуфбек |
| zaynab | зайнаб |
| oftob | офтоб |
| ziyo shohichi | зия-шахичи |
| musulmonqul | мусульманкул |
| azizbek | азизбек |
| marg'ilon | маргелан |
| toshkand | ташкент |
| o'zbek oyim | узбек-аим |
| usta alim | уста алим |
| qutidor | кутидор |
| sodiq | садык |
| mirzakarim | мирзакарим |
| gulsin | гульсун |
| xonimbibi | ханым |
| anorgul | анаргул |
| savra | савра |
| qo'rboshi | курбаши |
| devona | дивана |
| karimqul | каримкул |
 
### 3. Gale-Church DP
 
Within each anchor window the script runs a character-length-based DP. The cost of
aligning a span of UZ sentences to a span of RU sentences is `|1 − len_uz / (len_ru + 1)|`.
Six move types are supported:
 
| Move | Penalty | Rationale |
|------|---------|-----------|
| `1:1` | 0 | Exact correspondence |
| `1:2`, `2:1` | +0.1 | Common sentence-splitting/joining |
| `1:3`, `3:1` | +0.2 | Qodiriy's clause-heavy UZ compound sentences vs. RU's shorter renderings; kept as a last resort |
| `1:0`, `0:1` | length × 0.3 + 1 | Unmatched sentences (one language only) |
 
### 4. Conservation check
 
After alignment the script prints UZ and RU sentence totals derived from the type
breakdown. These must equal the raw tokenised counts as a sanity check:
 
```
UZ = 1:1 + 2×(2:1) + 1:2 + 1:3 + 3×(3:1) + 1:0
RU = 1:1 + 2:1 + 2×(1:2) + 3×(1:3) + 0:1 + 3:1
```
 
---
 
## Known Data Issues
 
### p3_ch15_ru.txt — duplicate block
 
Lines 65–79 of the Russian source file are a verbatim repeat of lines 50–64
(a copy-paste artefact). Before aligning, remove the duplicate:
 
```bash
sed '65,79d' p3_ch15_ru.txt > p3_ch15_ru_clean.txt
python align_single_chapter.py p3_ch15_uz.txt p3_ch15_ru_clean.txt p3_ch15_aligned.csv p3_ch15
```
 
### p3_ch16 / p3_ch17 — chapter-boundary mismatch
 
The UZ and RU editions divide the final material differently. UZ chapter 16 ends with
the full cemetery scene, the gravestone elegy, and Atabek's silent departure. The RU
translator closed chapter 16 earlier and opened chapter 17 with that same content,
followed by the epilogue. As a result:
 
- **UZ ch16** (pairs 277–309): 26 `1:0` orphans — the cemetery/departure scene has no
  RU counterpart in the same file.
- **RU ch17** (pairs 1–36): 28 `0:1` orphans — these are the RU version of the same
  scene, placed in the next chapter.
For corpus use, these two sets should be linked as a cross-chapter boundary pair. The
RU gravestone epitaph also adds an explicit anti-polygamy moral sentence absent from
the UZ original.
 
### p3_ch17 — UZ-only Author's Note
 
The UZ edition closes with a short authorial postscript ("YOZG'UCHIDAN") about the
historical fate of the character Yodgorbek. This has no counterpart in the Russian
edition and produces 5 `1:0` orphans at the end of the ch17 alignment.
 
---
 
## Recurring Alignment Patterns
 
The following patterns appear throughout the corpus and are documented in per-chapter
quality notes:
 
| Pattern | Description |
|---------|-------------|
| **Dialogue-granularity mismatch** | RU translator splits each speech act into its own line; UZ compounds them. Produces clusters of `0:1` orphans inside dialogue scenes. |
| **RU narrative expansion** | The translator adds narrator commentary or makes implicit UZ information explicit. Produces `0:1` orphans in expository passages. |
| **Anchor-free window drift** | Philosophical monologues or scenes with no named characters produce large anchor-free windows where the DP can cross-map content. Flagged in ch9, ch13, ch15. |
| **UZ compound → RU staccato** | Qodiriy's clause-heavy descriptive compounds (especially in emotional climaxes) are rendered as short punchy Russian sentences, producing `3:1` pairs or `1:0` orphans for the surrounding short UZ beats. |
| **RU translation compression** | The Russian translator substantially abridged several passages — most notably the entire funeral/cemetery/departure sequence at the end of ch16 (26 UZ sentences reduced to 4 RU summary sentences). |
 
---
 
## Citation
 
If you use this code or the resulting corpus, please cite:
 
> [Author(s)]. (*forthcoming*). *Title of article*. *Journal name*.
 
---
 
## Licence
 
Scripts: MIT.
The novel texts themselves are in the public domain in Uzbekistan (Abdulla Qodiriy, 1894–1938).
