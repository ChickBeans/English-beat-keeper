"""Generate on-the-beat model-voice clips with Kokoro (Apache-2.0).

Instead of time-stretching finished audio, this edits Kokoro's predicted
phoneme durations before the waveform is generated, so the voice is
synthesised already speaking in time:

* the onset (first consonant) of every stressed syllable lands exactly on a
  beat; weak syllables keep their natural proportions inside each beat,
* when a beat is longer than the natural phrase, sounds stretch at most
  MAX_STRETCH and the rest becomes a pause between words,
* one clip per BPM in BPMS; the app picks the nearest and stretches the
  whole clip uniformly by a few percent.

usage: python tools/make_voice.py index.html voice/ SET_INDEX [SET_INDEX ...]
"""
import json, re, sys, os
import numpy as np, soundfile as sf, torch
from kokoro import KPipeline

VOICE = "bf_emma"
BPMS = list(range(50, 131, 10))
SR, FRAME = 24000, 600            # Kokoro: one duration unit = 600 samples = 25 ms
FPS = SR / FRAME
MAX_STRETCH = 1.3
VOWELS = set("aeiouɑɐɒɔæəɘɚɛɜɝɞɤɨɪɯɵøœɶʉʊʌʏAIOWYQᵊ")
CAPS = set("AIOWYQ")
MARKS = set("ˈˌ")

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

def parse(line):
    words = []
    for wi, tok in enumerate(line.split()):
        core, trail = re.match(r"^(.*?)([.,!?]*)$", tok).groups()
        core = re.sub(r"\{.*\}$", "", core)
        parts = [p for h in core.split("-") for p in h.split("~")]
        clean = [p.replace("*", "") for p in parts]
        text = "".join(clean)
        if wi == 0 or text.lower() in proper: text = text[:1].upper() + text[1:]
        words.append(dict(text=text, trail=trail, n=len(parts), key="-".join(c.lower() for c in clean),
                          stress=[p.startswith("*") for p in parts]))
    return words

def tts_text(words):
    out = []
    for w in words:
        ent, t = IPA.get(w["key"], ""), w["text"]
        if not any(w["stress"]) and "|" in ent: t = "[%s](/%s/)" % (t, ent.split("|")[1])
        out.append(t + w["trail"])
    return " ".join(out)

def nuclei(ph):
    idx, prev, pc = [], False, ""
    for i, c in enumerate(ph):
        v = c in VOWELS
        if v and (not prev or pc in CAPS or c in CAPS or pc == "ː"): idx.append(i)
        if c not in MARKS: prev = v or (prev and c == "ː"); pc = c
    return idx

def syllable_onsets(ph, a, b, n):
    """char index where each of the n syllables of ph[a:b] starts (its first consonant)."""
    nu = [a + i for i in nuclei(ph[a:b])]
    if len(nu) != n: return None
    ons = [a]
    for k in range(1, n):
        j = nu[k - 1] + 1
        while j < nu[k] and (ph[j] in VOWELS or ph[j] == "ː"): j += 1   # end of previous nucleus
        cons = [i for i in range(j, nu[k]) if ph[i] not in MARKS]
        take = 0 if not cons else (1 if len(cons) == 1 else len(cons) - 1)
        ons.append(cons[-take] if take else nu[k])
    return ons

pipe = KPipeline(lang_code="b")
model = pipe.model
pack = pipe.load_voice(VOICE)

def synth(ps, dur):
    ids = torch.LongTensor([[0] + [model.vocab[p] for p in ps] + [0]]).to(model.device)
    ref_s = pack[len(ps) - 1].to(model.device)
    m = model
    with torch.no_grad():
        L = torch.full((1,), ids.shape[-1], dtype=torch.long)
        mask = torch.gt(torch.arange(L.max()).unsqueeze(0) + 1, L.unsqueeze(1))
        bert = m.bert(ids, attention_mask=(~mask).int())
        d_en = m.bert_encoder(bert).transpose(-1, -2)
        s = ref_s[:, 128:]
        d = m.predictor.text_encoder(d_en, s, L, mask)
        pd = torch.LongTensor(dur)
        idx = torch.repeat_interleave(torch.arange(ids.shape[1]), pd)
        aln = torch.zeros((ids.shape[1], idx.shape[0])); aln[idx, torch.arange(idx.shape[0])] = 1
        aln = aln.unsqueeze(0)
        en = d.transpose(-1, -2) @ aln
        F0, N = m.predictor.F0Ntrain(en, s)
        t_en = m.text_encoder(ids, L, mask)
        audio = m.decoder(t_en @ aln, F0, N, ref_s[:, :128]).squeeze()
    return audio.numpy()

def retime(nat, slots_by_seg, pause_slot, tgt):
    """scale durations of the slots in one beat so they sum to tgt frames."""
    total = sum(nat[i] for i in slots_by_seg)
    r = tgt / total
    new = {i: nat[i] * min(r, MAX_STRETCH) for i in slots_by_seg}
    new = {i: max(1, int(round(v))) for i, v in new.items()}
    left = tgt - sum(new.values())
    if left > 0 and r > MAX_STRETCH and pause_slot is not None: new[pause_slot] += left; left = 0
    order = sorted(slots_by_seg, key=lambda i: -nat[i])
    k = 0
    while left != 0 and k < 10000:            # spread rounding error over the longest sounds
        i = order[k % len(order)]
        if left > 0: new[i] += 1; left -= 1
        elif new[i] > 1: new[i] -= 1; left += 1
        k += 1
    return new

os.makedirs(outdir, exist_ok=True)
manifest = {"voice": VOICE, "sr": SR, "bpms": BPMS, "lines": {}}
for si in want:
    for li, (full, cue, short) in enumerate(ENTRY.findall(sets[si].split("lines:[", 1)[1])):
        for variant, line in (("full", full), ("short", short)):
            if not line: continue
            words = parse(line)
            r = list(pipe(tts_text(words), voice=VOICE))[0]
            ps, nat = r.phonemes, r.pred_dur.tolist()
            assert len(nat) == len(ps) + 2 and all(p in model.vocab for p in ps), line
            spans, p = [], 0
            for t in r.tokens:
                if not t.phonemes or not re.search(r"\w", t.text): continue
                j = ps.index(t.phonemes, p); spans.append((j, j + len(t.phonemes))); p = j + len(t.phonemes)
            assert len(spans) == len(words), line
            syl = []   # (key, char index of onset, stressed?)
            for wi, (w, (a, b)) in enumerate(zip(words, spans)):
                ons = syllable_onsets(ps, a, b, w["n"]) or [a + (b - a) * k // w["n"] for k in range(w["n"])]
                for k, o in enumerate(ons): syl.append(("%d:%d" % (wi, k), o, w["stress"][k], b))
            stress = [s for s in syl if s[2]]
            clips = []
            for bpm in BPMS:
                beat = FPS * 60 / bpm
                dur = list(nat)
                for j in range(len(stress) - 1):
                    c0, c1 = stress[j][1], stress[j + 1][1]
                    slots = list(range(c0 + 1, c1 + 1))               # slot = char index + 1
                    wend = stress[j][3]                                # end of the stressed word
                    pause = next((i + 1 for i in range(wend, c1) if ps[i] == " "), None)
                    # exact beat length, measured from the start of the line so rounding never drifts
                    tgt = int(round((j + 1) * beat)) - int(round(j * beat))
                    new = retime(nat, slots, pause, tgt)
                    for i, v in new.items(): dur[i] = v
                audio = synth(ps, dur)
                start = np.cumsum([0] + dur)
                at = lambda c: round(float(start[c + 1] / FPS), 4)
                anchors = {k: at(o) for k, o, _, _ in syl}
                first = at(stress[0][1])
                end = round(float(start[spans[-1][1] + 1] / FPS), 4)
                fn = "s%d_l%d_%s_%d.wav" % (si, li, variant, bpm)
                sf.write(os.path.join(outdir, fn), audio, SR, subtype="PCM_16")
                clips.append(dict(bpm=bpm, file=fn, anchors=anchors, first=first, end=end))
                got = [round((anchors[s[0]] - first) * bpm / 60, 3) for s in stress]
                assert all(abs(g - i) < 0.06 for i, g in enumerate(got)), (line, bpm, got)
            manifest["lines"]["%d:%d:%s" % (si, li, variant)] = clips
            print(si, li, variant, tts_text(words))
json.dump(manifest, open(os.path.join(outdir, "manifest.json"), "w"), ensure_ascii=False, separators=(",", ":"))
