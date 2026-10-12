"""Write docs/PHRASES.md: every line of the paid scenes and the consonant scene, for review."""
import re
s = open("index.html", encoding="utf-8").read()
blk = s[s.index("const SETS=["):s.index("const IPA=")]
sets = re.split(r"\n ,?\{", blk)[1:]
ENTRY = re.compile(r'\["((?:[^"\\]|\\.)*)","((?:[^"\\]|\\.)*)"(?:,"((?:[^"\\]|\\.)*)")?\]')
names = {"biz": "Business", "daily": "日常会話", "travel": "旅行", "cons": "子音トレーニング"}
out = ["# 有料カテゴリと子音トレーニングの例文", "",
       "`python tools/list_phrases.py` でアプリの `SETS` から書き出した一覧です。`*` が付いた音節が強い音（拍）です。", "",
       "作り方のルール:",
       "- Business・日常会話・旅行は、**時制を変えて文字を増やさない**。",
       "  - 拍が固定のセット: 丁寧さ（can you → could you → could you just）、me・for me・with us などの代名詞、so・and・then などのつなぎで弱い音を増やす。",
       "  - 「応用」セット: よく使う表現を1つずつ足していく（拍も増える）。",
       "- 子音トレーニングは早口言葉の形で、特定の子音を集中的に練習する。拍の数は固定で、足していく弱い音にも、なるべくその子音を入れる。", ""]
for sc, title in names.items():
    out += ["## " + title, ""]
    n = 0
    for st in sets:
        if 'scene:"%s"' % sc not in st[:40]: continue
        n += 1
        base = re.findall(r'"([^"]+)"', re.search(r"base:(\[[^\]]*\])", st).group(1))
        lines = ENTRY.findall(st.split("lines:[", 1)[1])
        beats = [l[0].count("*") for l in lines]
        tag = ("応用 %d→%d拍" % (beats[0], beats[-1])) if "grow:true" in st[:60] else ("%d拍" % beats[0])
        out += ["### %d. %s（%s）" % (n, ", ".join(base), tag), "| Lv | 文 | 追加したもの |", "|---|---|---|"]
        for k, (f, c, sh) in enumerate(lines):
            out.append("| %d | %s | %s |" % (k + 1, f + (" ／ 短縮: " + sh if sh else ""), c))
        out.append("")
open("docs/PHRASES.md", "w", encoding="utf-8").write("\n".join(out))
print("docs/PHRASES.md", len(out), "lines")
