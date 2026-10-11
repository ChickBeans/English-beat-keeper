"""Generate beat-alignable model-voice clips with Kokoro (Apache-2.0).

Reads the SETS / IPA tables from index.html, renders each line (full and
contracted forms) at a few speaking rates, and writes WAV clips plus a
manifest with the onset time of every syllable's vowel (key "word:syllable",
matching the app's syllable keys). The app time-stretches each clip so these
onsets land on the scheduled syllable times.

usage: python tools/make_voice.py index.html voice/ SET_INDEX [SET_INDEX ...]
"""
import json, re, sys, os
import numpy as np, soundfile as sf
from kokoro import KPipeline

VOICE = "bf_emma"
SPEEDS = [0.75, 0.95, 1.2]
SR = 24000
FRAME = 600  # samples per predicted-duration frame
VOWELS = set("aeiouɑɐɒɔæəɘɚɛɜɝɞɤɨɪɯɵøœɶʉʊʌʏAIOWYQᵊ")
CAPS = set("AIOWYQ")

src = open(sys.argv[1], encoding="utf-8").read()
outdir = sys.argv[2]; want = [int(x) for x in sys.argv[3:]]
IPA = json.loads(re.search(r"const IPA=(\{.*?\});\n", src).group(1))
blk = src[src.index("const SETS=["):src.index("const IPA=")]
ENTRY = re.compile(r'\["((?:[^"\\]|\\.)*)","((?:[^"\\]|\\.)*)"(?:,"((?:[^"\\]|\\.)*)")?\]')
sets = re.split(r"\n ,?\{", blk)[1:]
proper = {"i"}
for st in sets:
    for b in re.findall(r'"([^"]+)"', re.search(r"base:\[([^\]]*)\]", st).group(1)):
        if b[:1].isupper(): proper.add(b.lower())
    m = re.search(r"proper:\[([^\]]*)\]", st)
    if m: proper |= {x.lower() for x in re.findall(r'"([^"]+)"', m.group(1))}

def parse(line):
    words = []
    for wi, tok in enumerate(line.split()):
        core, trail = re.match(r"^(.*?)([.,!?]*)$", tok).groups()
        core = re.sub(r"\{.*\}$", "", core)
        parts = [p for h in core.split("-") for p in h.split("~")]
        clean = [p.replace("*", "") for p in parts]
        text = "".join(clean)
        if wi == 0 or text.lower() in proper: text = text[:1].upper() + text[1:]
        key = "-".join(c.lower() for c in clean)
        stressed = any(p.startswith("*") for p in parts)
        words.append(dict(text=text, trail=trail, n=len(parts), key=key, stressed=stressed))
    return words

def tts_text(words):
    out = []
    for w in words:
        ent = IPA.get(w["key"], "")
        t = w["text"]
        if not w["stressed"] and "|" in ent:  # force the weak form of function words
            t = "[%s](/%s/)" % (t, ent.split("|")[1])
        out.append(t + w["trail"])
    return " ".join(out)

def nuclei(ph):
    idx, prev, pc = [], False, ""
    for i, c in enumerate(ph):
        v = c in VOWELS
        # a vowel starts a new syllable unless it continues a short vowel (e.g. ɪə, eə)
        if v and (not prev or pc in CAPS or c in CAPS or pc == "ː"): idx.append(i)
        if c != "ˈ" and c != "ˌ":
            prev = v or (prev and c == "ː"); pc = c
    return idx

pipe = KPipeline(lang_code="b")
os.makedirs(outdir, exist_ok=True)
manifest_path = os.path.join(outdir, "manifest.json")
manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {"voice": VOICE, "sr": SR, "lines": {}}

for si in want:
    ents = ENTRY.findall(sets[si].split("lines:[", 1)[1])
    for li, (full, cue, short) in enumerate(ents):
        for variant, line in (("full", full), ("short", short)):
            if not line: continue
            words = parse(line)
            clips = []
            for sp in SPEEDS:
                res = list(pipe(tts_text(words), voice=VOICE, speed=sp))
                assert len(res) == 1, line
                r = res[0]
                audio = r.audio.numpy(); pd = r.pred_dur.tolist()
                start = np.cumsum([0] + pd)  # frame index where each phoneme slot starts
                ph = r.phonemes
                # locate each token's phoneme span in the phoneme string
                spans, p = [], 0
                for t in r.tokens:
                    if not t.phonemes or not re.search(r"\w", t.text): continue
                    j = ph.index(t.phonemes, p); spans.append((t.text, j, j + len(t.phonemes))); p = j + len(t.phonemes)
                assert len(spans) == len(words), (line, spans)
                anchors = {}
                for wi, (w, (txt, a, b)) in enumerate(zip(words, spans)):
                    nu = nuclei(ph[a:b])
                    t0 = start[a + 1] * FRAME / SR; t1 = start[b + 1] * FRAME / SR
                    if len(nu) == w["n"]:
                        ts = [start[a + k + 1] * FRAME / SR for k in nu]
                    else:  # fall back to spreading syllables over the word
                        ts = [t0 + (t1 - t0) * k / w["n"] for k in range(w["n"])]
                        print("  syllable mismatch:", w["text"], ph[a:b], len(nu), "vs", w["n"])
                    for k, t in enumerate(ts): anchors["%d:%d" % (wi, k)] = round(float(t), 4)
                last = spans[-1][2]
                speech_end = start[last + 1] * FRAME / SR
                fn = "s%d_l%d_%s_%d.wav" % (si, li, variant, int(sp * 100))
                sf.write(os.path.join(outdir, fn), audio, SR, subtype="PCM_16")
                clips.append(dict(rate=sp, file=fn, anchors=anchors, end=round(float(speech_end), 4), len=round(len(audio) / SR, 4)))
            manifest["lines"]["%d:%d:%s" % (si, li, variant)] = clips
            print(si, li, variant, tts_text(words))
json.dump(manifest, open(manifest_path, "w"), ensure_ascii=False, separators=(",", ":"))
