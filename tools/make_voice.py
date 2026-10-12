"""Generate on-the-beat model-voice clips with Kokoro (Apache-2.0).

Instead of time-stretching finished audio, this edits Kokoro's predicted
phoneme durations before the waveform is generated, so the voice is
synthesised already speaking in time:

* the onset (first consonant) of every stressed syllable lands exactly on a
  beat; weak syllables keep their natural proportions inside each beat,
* when a beat is longer than the natural phrase, it is lengthened the way
  speakers slow down: mostly the stressed vowel (up to VOWEL_MAX), a little
  on continuant consonants (up to CONT_MAX), never stops or weak syllables,
  and at most MAX_STRETCH of the beat's natural length. The rest becomes
  real silence after the stressed word, which first decays to FADE_FLOOR
  (Kokoro smears long "space" tokens, so the pause is spliced into the
  waveform instead),
* one clip per BPM in BPMS; the app picks the nearest and stretches the
  whole clip uniformly by a few percent.

usage: python tools/make_voice.py index.html voice/ SET_INDEX [SET_INDEX ...]
"""
import json, re, sys, os
import numpy as np, soundfile as sf, torch
from kokoro import KPipeline

VOICE = "bf_emma"
BPMS = list(range(80, 161, 10))
MIN_SQUEEZE = 0.6   # a beat may not be shorter than 60% of its natural length
PAUSE_OK = 0.15     # silence per beat we tolerate (s); slower tempos get no AI voice
SR, FRAME = 24000, 600            # Kokoro: one duration unit = 600 samples = 25 ms
FPS = SR / FRAME
MAX_STRETCH = 1.3
VOWEL_MAX, CONT_MAX = 1.6, 1.2
CONTINUANTS = set("mnŋlɹrwjhfvθðszʃʒ")
FADE_FLOOR = 0.05
# stress contrast: weak syllables quieter, shorter and lower; stressed ones a little higher
WEAK_GAIN, WEAK_DUR, WEAK_F0, STRESS_F0 = 10 ** (-12 / 20), 0.8, 0.96, 1.1
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

def synth(ps, dur, f0mul=None):
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
        if f0mul is not None:                       # one factor per duration frame; F0 runs at 2x
            fm = torch.FloatTensor(np.repeat(f0mul, 2))[None, :F0.shape[-1]]
            F0 = F0 * fm
        t_en = m.text_encoder(ids, L, mask)
        audio = m.decoder(t_en @ aln, F0, N, ref_s[:, :128]).squeeze()
    return audio.numpy()

def retime(nat, slots, can_pause, tgt, cap):
    """durations for the slots of one beat, plus frames of silence to add, summing to tgt.
    cap[i] is how far slot i may stretch (stressed vowel > continuant > everything else)."""
    total = sum(nat[i] for i in slots)
    pause = 0
    if tgt <= total:                             # compress: scale evenly
        new = {i: nat[i] * tgt / total for i in slots}
    else:
        extra = tgt - total
        budget = min(extra, total * (MAX_STRETCH - 1))
        new = {i: float(nat[i]) for i in slots}
        for level in (VOWEL_MAX, CONT_MAX):      # natural lengthening: vowels first, then continuants
            room = {i: nat[i] * (min(cap[i], level) - 1) for i in slots if cap[i] >= level}
            tot = sum(room.values())
            if tot <= 0 or budget <= 0: continue
            use = min(budget, tot)
            for i, r in room.items(): new[i] += r * use / tot
            budget -= use
        rest = tgt - sum(new.values())
        if can_pause: pause = min(rest, PAUSE_OK * FPS); rest -= pause   # a short breath at most
        if rest > 0:                             # chant: hold the stressed vowel (then continuants)
            for level in (VOWEL_MAX, CONT_MAX, 1.0):
                hold = [i for i in slots if cap[i] >= level]
                if hold:
                    tot = sum(nat[i] for i in hold)
                    for i in hold: new[i] += rest * nat[i] / tot
                    break
    new = {i: max(1, int(round(v))) for i, v in new.items()}
    goal = tgt - int(round(pause))
    left = goal - sum(new.values())
    order = sorted(slots, key=lambda i: -nat[i])
    k = 0
    while left != 0 and k < 10000:            # spread rounding error over the longest sounds
        i = order[k % len(order)]
        if left > 0: new[i] += 1; left -= 1
        elif new[i] > 1: new[i] -= 1; left += 1
        k += 1
    return new, tgt - sum(new.values())

def splice(audio, pauses):
    """pauses: (word start sample, word end sample, n silent samples). The end of the word
    decays to FADE_FLOOR along an ease-in curve (slow at first, faster at the end), then a
    6 ms fade to zero and the silence."""
    fade = int(SR * .006)
    for w0, pos, n in sorted(pauses, key=lambda p: -p[1]):
        if n <= 0: continue
        L = max(int(SR * .08), int((pos - w0) * .4)); L = min(L, pos - w0)
        x = np.linspace(0, 1, L)
        a, b = audio[:pos].copy(), audio[pos:].copy()
        a[-L:] *= 1 - (1 - FADE_FLOOR) * x ** 2
        a[-fade:] *= np.linspace(1, 0, fade); b[:fade] *= np.linspace(0, 1, fade)
        audio = np.concatenate([a, np.zeros(n, dtype=audio.dtype), b])
    return audio

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
            # stressed flag for every phoneme char (spaces belong to the syllable before them)
            cflag = [False] * len(ps)
            for i, (_, o, st, _) in enumerate(syl):
                o2 = syl[i + 1][1] if i + 1 < len(syl) else len(ps)
                for c in range(o, o2): cflag[c] = st
            base = list(nat)
            for c in range(len(ps)):
                if not cflag[c] and ps[c] not in " .,!?": base[c + 1] = max(1, base[c + 1] * WEAK_DUR)
            # slowest tempo this line can be spoken at without long gaps: every beat's stretched
            # length (+ a short natural pause) must still fill the beat
            def capof(i):
                c = ps[i - 1]
                return (VOWEL_MAX if (c in VOWELS or c == "ː") else CONT_MAX if c in CONTINUANTS else 1.0) if cflag[i - 1] else 1.0
            longest_ok, shortest_ok = None, 0
            for j in range(len(stress) - 1):
                sl = range(stress[j][1] + 1, stress[j + 1][1] + 1)
                tot = sum(base[i] for i in sl); room = sum(base[i] * (capof(i) - 1) for i in sl)
                ok = (tot + min(room, tot * (MAX_STRETCH - 1))) / FPS + PAUSE_OK
                longest_ok = ok if longest_ok is None else min(longest_ok, ok)
                shortest_ok = max(shortest_ok, tot * MIN_SQUEEZE / FPS, (stress[j + 1][1] - stress[j][1]) / FPS)
            minbpm = 60 / longest_ok if longest_ok else BPMS[0]
            maxbpm = 60 / shortest_ok if shortest_ok else BPMS[-1]
            use = BPMS
            clips = []
            for bpm in use:
                beat = FPS * 60 / bpm
                dur = [max(1, int(round(v))) for v in base]; pauses = []   # (char index the pause goes before, frames)
                for j in range(len(stress) - 1):
                    c0, c1 = stress[j][1], stress[j + 1][1]
                    slots = list(range(c0 + 1, c1 + 1))               # slot = char index + 1
                    wend = stress[j][3]                                # end of the stressed word
                    gap = next((i for i in range(wend, c1) if ps[i] == " "), None)
                    # exact beat length, measured from the start of the line so rounding never drifts
                    tgt = int(round((j + 1) * beat)) - int(round(j * beat))
                    cap = {}
                    for i in slots:
                        c = ps[i - 1]
                        cap[i] = (VOWEL_MAX if (c in VOWELS or c == "ː") else CONT_MAX if c in CONTINUANTS else 1.0) if cflag[i - 1] else 1.0
                    new, extra = retime(base, slots, gap is not None, tgt, cap)
                    for i, v in new.items(): dur[i] = v
                    if extra > 0: pauses.append((gap, extra, c0))
                start = np.cumsum([0] + dur)
                f0mul = np.ones(int(start[-1]))
                for c in range(len(ps)):
                    if ps[c] in " .,!?": continue
                    f0mul[int(start[c + 1]):int(start[c + 2])] = STRESS_F0 if cflag[c] else WEAK_F0
                audio = synth(ps, dur, f0mul)
                gain = np.ones(len(audio))
                for c in range(len(ps)):
                    if not cflag[c]: gain[int(start[c + 1]) * FRAME:int(start[c + 2]) * FRAME] = WEAK_GAIN
                w = int(SR * .02); gain = np.convolve(np.pad(gain, (w, w), "edge"), np.ones(w) / w, "same")[w:-w]
                audio = (audio * gain[:len(audio)]).astype(np.float32)
                audio = splice(audio, [(int(start[w + 1] * FRAME), int(start[c + 1] * FRAME), f * FRAME) for c, f, w in pauses])
                shift = lambda c: sum(f for g, f, _ in pauses if g < c)    # silence inserted before char c
                at = lambda c: round(float((start[c + 1] + shift(c)) / FPS), 4)
                anchors = {k: at(o) for k, o, _, _ in syl}
                first = at(stress[0][1])
                end = at(spans[-1][1])
                fn = "s%d_l%d_%s_%d.wav" % (si, li, variant, bpm)
                sf.write(os.path.join(outdir, fn), audio, SR, subtype="PCM_16")
                clips.append(dict(bpm=bpm, file=fn, anchors=anchors, first=first, end=end))
                got = [round((anchors[s[0]] - first) * bpm / 60, 3) for s in stress]
                if not all(abs(g - i) < 0.06 for i, g in enumerate(got)):   # too dense to fit this tempo
                    clips.pop(); os.remove(os.path.join(outdir, fn)); print("  skip", bpm, "BPM (cannot fit)")
            manifest["lines"]["%d:%d:%s" % (si, li, variant)] = clips
            manifest.setdefault("range", {})["%d:%d:%s" % (si, li, variant)] = [int(round(minbpm)), int(round(maxbpm))]
            print(si, li, variant, "%d-%d BPM" % (round(minbpm), round(maxbpm)), [c["bpm"] for c in clips], tts_text(words))
json.dump(manifest, open(os.path.join(outdir, "manifest.json"), "w"), ensure_ascii=False, separators=(",", ":"))
