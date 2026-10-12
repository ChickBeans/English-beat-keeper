# 人が「ノれる」音楽の作り方：研究のまとめとセッションモードの設計ルール

最終更新: 2026-10-12

セッションモード（BGM）の音作りの根拠をまとめたメモです。新しいスタイルを作るとき、既存のスタイルを直すときは、このルールに沿って作ります。

---

## 1. 研究から分かっていること

| # | 分かっていること | 研究 |
|---|---|---|
| 1 | **低い音のほうがリズムを取りやすい。** 2つの音が同時に鳴ると、低い音のタイミングのズレのほうがよく気づかれ、手拍子も低い音に引っぱられる。 | Hove, Marie, Bruce & Trainor (2014) PNAS 111(28)。※Wojtczak ら (2017) PNAS は仕組みの説明に異論あり |
| 2 | **低音だと脳が拍をよりはっきり追う。** リズムを低い音（130Hz）で鳴らすと、高い音で鳴らすより、拍の周期の脳波が強くなる。複雑なリズムほど効果が大きい。 | Lenc, Keller, Varlet & Nozaradan (2018) PNAS 115(32) |
| 3 | **ベースが低いほど「ノれる」と感じ、手拍子も安定する。** 低音の音量や音色が拍ごとに変化する曲ほど、ノれると評価される。 | Stupacher, Hove & Janata (2016) Music Perception |
| 4 | **耳で聞こえない超低音（8〜37Hz）を足すだけで、ライブの観客が約12%多く踊った。** | Cameron ら (2022) Current Biology 32(21) |
| 5 | **拍を刻む楽器はタイミングが正確なほうがノれる。** ドラムを15〜25msずらすと評価が下がり、早くずらすと特に下がる。例外は単純なシャッフル（ハネ）。 | Frühauf, Kopiez & Platz (2013)、Davies ら (2013) Music Perception |
| 6 | **シンコペーション（拍からずらしたリズム）は中くらいが一番ノれて気持ちいい（逆U字）。** 少なすぎると退屈、多すぎると拍を見失う。 | Witek ら (2014) PLoS ONE 9(4) |
| 7 | **和音は単純〜中くらいの複雑さがいい。** 複雑すぎる和音は、リズムの気持ちよさを弱める。 | Matthews ら (2019) PLoS ONE 14(1) |
| 8 | **遅いテンポは、拍と拍の間に細かい刻みがあると合わせやすい**（subdivision benefit）。 | Repp (2003, 2011 ほか) |
| 9 | **予想どおりと予想外が混ざっているときに、一番気持ちいい。** 繰り返しの中に、ときどき変化を入れるのがいい。 | Gold ら (2019) J. Neuroscience 39(47) |
| 10 | **声と似た音が同時に鳴ると、聞き取りが大きく落ちる**（情報マスキング）。同じ帯域にエネルギーがぶつかる「エネルギー的マスキング」より影響が大きいことがある。 | Brungart (2001) JASA 110(5) |
| 11 | 言葉の聞き取りには、中〜高めの帯域（目安は1〜4kHz）が大きく効く。 | 音声明瞭度指数（SII、ANSI S3.5-1997）の考え方。帯域ごとの正確な重みは規格の表を参照 |

## 2. このアプリの設計ルール

| ルール | 中身 | 根拠 |
|---|---|---|
| **R1. 拍は低音で刻む** | キックとベースの頭は必ず拍に置く。ベースには1オクターブ下の音を足す。 | 1〜4 |
| **R2. 拍を刻む楽器はグリッドぴったり** | キック・スネア・ベースはずらさない。ハネ（スイング）はハイハットとメロディだけにする。 | 5 |
| **R3. シンコペーションは「中」** | キックとスネアの位置は固定して、拍を見失わないようにする。ずらすのは1小節に2〜4か所まで（ベース・コード・ゴーストノート）。 | 6 |
| **R4. 和音はシンプルに** | 2〜4つのコードを繰り返す。9thまでにして、b9などの強い緊張音は使わない。 | 7 |
| **R5. 遅いテンポでは細かく刻む** | BPM 100未満では、16分音符のハイハットを常に鳴らす。 | 8 |
| **R6. 繰り返し＋ときどき変化** | 4小節ごとにセクションを抽選する（Bメロ・サビ・Cメロ）。サビ・Cメロの直前は、溜めて落とす（ベースを2拍抜いて、スネアを連打）。 | 9 |
| **R7. 拍の頭を一番強く** | 1拍目（ファンクでいう「the One」）を一番強いアクセントにする。 | 1・2、拍の階層 |
| **R8. 声の邪魔をしない** | 下の3つで、声が鳴っている間（AI声の番も、交互モードで自分が言う番も）を空ける。 | 10・11 |

R8の中身:
- **メロディは声の隙間で鳴らす（コール＆レスポンス）。** 声が鳴っている間は、メロディ楽器を鳴らさない。鳴らしても高音の小さな飾りだけにする。
- **声が鳴っている間は、BGM全体に帯域のくぼみを作る**（イコライザーで削る。2.2kHzを−8dB、700Hzを−4dB）。
- **伴奏は、声の間は1オクターブ下で軽く弾く。**

## 3. スタイルごとの当てはめ

| スタイル | R1 低音 | R2/R3 リズム | R4 和音 | R8 声の空け方 |
|---|---|---|---|---|
| Lo-fi | キックとベース＋下のオクターブ | ハネはハイハットだけ。ハーフタイムはBPM 140以上 | 9thまで | 背景の音が少なめ（くぼみ処理はなし） |
| クラブ | 正弦波のサブベース、キックに合わせてベースが引っ込む | 四つ打ちとベースのうねり | 三和音 | AI声の下で背景の音量を下げる（くぼみ処理はなし） |
| ファンク | 親指で弾くスラップの低音、1拍目を一番強く | 16分のハイハット、ゴーストノート、スラップのオクターブで2〜4か所ずらす | 2コードの繰り返し | ホーンとエレピは隙間だけ。クラビとギターの刻みは声の間は半分の音量。くぼみ処理あり |
| French | 弾むベース（ルート・5度・オクターブ） | 1拍目と3拍目にキック、2拍目と4拍目にブラシのスネア | maj7・7th | ビブラフォン・アコーディオン・「バ・バ・バ」コーラスは隙間だけ。伴奏は声の間は1オクターブ下。くぼみ処理あり |

## 4. 今後見たいこと

- 録音機能のデータを使って、スタイルごとに「拍とのズレ」がどれだけ違うかを測る（BGMあり・なしの比較も）。
- 声の聞き取りやすさを、くぼみ処理あり・なしで比べる。

## 出典

- [Hove et al. 2014, PNAS](https://pmc.ncbi.nlm.nih.gov/articles/PMC4104866)
- [Lenc et al. 2018, PNAS](https://pmc.ncbi.nlm.nih.gov/articles/PMC6094140/)
- [Stupacher, Hove & Janata 2016, Music Perception](https://escholarship.org/uc/item/2sw3r2dw)
- [Cameron et al. 2022, Current Biology（McMaster 発表）](https://news.mcmaster.ca/?p=19202)
- [Microtiming 研究のレビュー（Frühauf 2013 / Davies 2013 を含む）](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2016.01487/pdf)
- [Witek et al. 2014, PLoS ONE](https://research.birmingham.ac.uk/en/publications/syncopation-body-movement-and-pleasure-in-groove-music/)
- [Matthews et al. 2019, PLoS ONE](https://pmc.ncbi.nlm.nih.gov/articles/PMC6328141)
- [Repp: subdivision benefit](https://labs.sonicfield.org/library/self-generated-interval-subdivision-reduces-variability-of-synchronization-with-)
- [Gold et al. 2019, J. Neuroscience](https://pmc.ncbi.nlm.nih.gov/articles/PMC6867811)
- [Brungart 2001, JASA](https://scholar.usuhs.edu/en/publications/informational-and-energetic-masking-effects-in-the-perception-of--2/)
- [Speech Intelligibility Index (ANSI)](https://blog.ansi.org/speech-intelligibility-index)
