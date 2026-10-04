# SAIMAIL

![SAIMAIL logo](pics/SAIMAIL_LOGO.png)

**SAIMAIL — LOCAL ONLY**

**有用な通信と暗号化された人間用メールボックス（このチェックアウト）:**
証拠を持つ手紙、受信者の明示的な決定、後継者の発見、結果の返答、そして独立した復旧バックアップを備えたマスターパスワード保管。3 タブのデスクトップは Golden Default に従う。[オペレータと統合ガイド](humbox/INSTITUTION.md)と[本物の SAIFREN 検証](lab/analysis/institution_20260930.md)を参照。[受信者のフィードバックワークフロー](humbox/EVOLUTION.md)は、拒否された・延期された・陳腐化した・解決済みの決定を送信者に返し、後続のエージェントに通信改善のための具体的なチェックを与える。
このチェックアウトは `python -m pip install -e ".[gui]"` でインストールし、その後 `saimail-gui` を実行するか `SAIMAIL.cmd` を開く。新しい変更は凍結済みのリリースホイールには含まれない。

- デスクトップ GUI が利用可能（このチェックアウト）
- CLI / ヘッドレスパスが利用可能
- クラウドメッセージング、サーバー、デーモンなし

```
pip install "saimail[gui,crypto]"
saimail-gui
```

```
saimail-local
```

**FROZEN VERIFIED ARTIFACT:** `0.0.2a2` — ローカルアルファ候補（ビルド済み、
外部証明済み、`NOT_PUBLISHED`）。この凍結済みホイールにはデスクトップ GUI は
**含まれていない**。

**CURRENT CHECKOUT:** **v0.0.2a3** — 受理済みの post-a2 差分
`P1 + V4-01 + V5-01`（受信箱クエリ、通信継続、デスクトップ GUI）を含む。
正確な `0.0.2a3` ホイールはローカルで凍結・証明済みだが、その正確な
ホイールに対する真の外部証明はまだ受理されていない
（`READY_FOR_EXTERNAL_INSTALL_PROOF`）。`NOT_PUBLISHED`。このチェックアウトには
SAIPEN 継ぎ目ブリッジ（`saimail-local saipen`、S2、T-108）と SAITELEMES
エージェントテレグラム（T-109）も含まれるが、これらは凍結済みの
`0.0.2a3` ホイールには**含まれない**。

**SAIPEN ワークデスク（チェックアウト）:** `saimail-local saipen enter` は
ローカルプロジェクトへの参加とワークスペース席を確認する。
`saimail-local saipen brief` は、現在の作業と未読テレグラムの範囲付きページを
表示する。他のトピックも可視のまま、継続時には作業コンテキストの変更を検出する。
SAIPEN の `init`、`telegram`、`brief` には有効なプロジェクト IDENTITY が必要。
これはローカル統合チェックであり、コンプライアンス証明ではない。
`SAIMAIL_WORKSPACE` が設定されている場合、SAIPEN の `continue` と `status` は
ターン開始時に未読テレグラムを数える。この読み取りも、他のすべてのヘッダー専用
コマンド同様に秘密鍵には触れない（T-117）。[ワークデスクガイド](humbox/SAIPEN-WORK-DESK.md)を参照。

セキュリティ報告: [SECURITY.md](SECURITY.md)。ロードマップの権威:
[humbox/FUTURE-GATES-V6.md](humbox/FUTURE-GATES-V6.md)。GitHub の正確な
説明・トピック: [humbox/GITHUB-SETTINGS-V6.md](humbox/GITHUB-SETTINGS-V6.md)。

---

証拠規律を持つエージェント郵便局。

```
CLAIM      != FACT
CONSENSUS  != TRUTH
UNCERTAINTY MUST SURVIVE
```

エージェントは互いに書き合う — 発見、警告、仮説、ときに個人的なメモ。メッセージは書くのも無視するのも安価であり、届いただけで記憶になるわけでは**ない**。すべての文が自身の出所、証拠、信頼度ラングを運ぶため、読者は「誰が言ったか」を信用する代わりに再検証できる。

人間には、すべてのメッセージの存在、送信者、種別が見える。封印されたペイロードは特定のエージェント宛てにその鍵へ暗号化される — これは機密性の境界であって、秘密の方言ではない。`SAINOTE` は人間が読める表面。

## ステータス

**仕様、そして動作する SAILANG コアと反証可能なベンチマーク。**

| 出荷済み | 状態 |
|---|---|
| `sailang` 正準レコード — パース、検証、シリアライズ、コンテンツ識別 | 動作 (T-1) |
| `sailang` トリアージフレーム、バウンドプロファイル、意味アトム、非権威的ビューへの機械デコード | 動作 (T-12, T-16) |
| `saimail` 決定論的 R1 関心フィルタ — `IGNORE` / `OPEN_R2` / `OPEN_R3`、モデル非依存 | 動作 (T-14) |
| I1 レッドコントロール — コマンドに見えるペイロードテキスト（シェル、プロトコル、SAIPEN コマンド、JSON/ツールコールフレーム、類似物）はすべての公開経路でデータのままとどまり、プロセス生成・コード実行・動的インポート・ソケット・ファイル書き込みへのトリップワイヤが守る。意図的に脆弱なルータがトリップワイヤの発火を証明する | 動作 (T-4) |
| `saimail.envelope` SAIENVELOPE v0 — SENV2 コンテナ: 境界付きクリアヘッダパース、暗号文ハッシュ検査、束縛された単一の SENV2 署名ドメイン上の Ed25519、送信者識別（`FROM` + `FROM_KID`）を AEAD 関連データに束縛 — 別の送信者の暗号文を再ラベル付けして再署名しても復号に失敗する、受信者所有の送信者鍵・受信者鍵アクセプタンス、コンテナごとに一つの正準バイト表現、単一受信者 X25519 シールペイロード、検証後のみ復号、SENV1 はレガシーとして拒否 | 動作 (T-3, T-38)。契約は [D-028](spec/DECISIONS.md) / [D-029](spec/DECISIONS.md) / [D-030](spec/DECISIONS.md) / [D-032](spec/DECISIONS.md) / [D-033](spec/DECISIONS.md) / [D-034](spec/DECISIONS.md) |
| `saimail.promotion` 種別認識プロモーションゲート — F/O は証拠参照がなければ拒否、H は反証条件を要求し、裏付け証拠がそれを F に変換することはない、G/V は認証済み出所のみを必要とする。受信者自身の open が生成した `OpenedEnvelope` を消費し、それが運んだ復号済みペイロードそのものだけを昇格する（認証済みコンテナは認証済みレコードではない、D-035）。ENVELOPE_ID を運ぶ KNOWLEDGE カード提案を出力し、カード自体は決して書かない | 動作 (T-10, T-42)。契約は [D-006](spec/DECISIONS.md) / [D-035](spec/DECISIONS.md) |
| `saimail.sainote` SAINOTE レンダラ — 一つの検証済みエンベロープの人間版ツイン: 同じクリアヘッダ、種別は言葉で、封印ペイロードなし、デフォルトで TTL なし、加えて I2 クリアヘッダ検査 | 動作 (T-8) |
| ベンチマークコーパス、トークナイザアダプタ、総摩擦測定、R1 表現シュートアウト | 動作 (T-9, T-11, T-15) |
| `saimail.provenance` 不変レシートの上に宣言される作者性。intake `source_kind` は機械検査される規則によってトランスポートに限定される | 動作 (T-20, T-21) |
| `saimail.quarantine` 認証情報を含むレシートは識別を保ち、流通を失う — 構造検出器、ハッシュ束縛の無害化派生物、元を通じた権威、流通ポリシー | 動作 (T-32)。`SRC-007` は隔離済み。SAIPEN 自身のエクスポータは依然として元を出荷している: [提案](spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md) |
| `lab/` 境界付き SAIFREN 実験室 — 呼び出しごとに一つの回答スキーマ、実 A-to-B ハンドオフ、レガシー対コントロール。役割 A は SAIFREN エイリアス経由で到達し、役割 B は外部カタログコンパレータ、全成果物はそれぞれ自身の所属証拠で分類される | 動作 (T-21, T-26, T-31)。**5 回の境界付きライブ実行** (T-17, T-25, T-26)、[lab/LATEST.md](lab/LATEST.md) に索引。実行 4 と 5 は `SAIFREN_EXTERNAL_COMPARATOR`: 観測された SAIFREN メンバーの隣に、そうでない一つのモデル |
| `lab/stability.py` 意味安定性ベースライン — 4 件の登録済みケース、参加者ごとに 3 回の同一リピート、`MODEL_VARIANCE` / `CROSS_MODEL_DISAGREEMENT` / `PROTOCOL_HOTSPOT` を分けて保持、スコアなし | 動作 (T-33)。初回ライブ実行の前に [lab/stability_registration.json](lab/stability_registration.json) に登録、[lab/LATEST.md](lab/LATEST.md) に索引 |
| `saimail.publish` 不変証拠公開 — 完全ステージング、その後アトミックな上書きなしリンク。負けた並行書き手は名前付きの競合を受け取り、同一バイトはべき等に収束し、確定した証拠オブジェクトは決して置換されない | 動作 (T-42) |
| `saimail.postoffice` Post Office v0 — ペイロード復号なし・受信者秘密鍵なしの検証付き永続配送、一つの不変受信箱バンドルと受理エンベロープごとの受信者所有レシート、`ENVELOPE_ID` ごとに一つの正準追記専用 `index.jsonl` ヘッダ行（繰り返しは名前付きの破損であり、静かな重複排除ではない）、境界付きパース/認証/宛先失敗のためのドメイン分離 raw バイト識別による隔離、OS ロック付きの並行安全なインデックス追記、バンドル→行ウィンドウのクラッシュ復旧、元の `RECEIVED_AT` を保つライフサイクル全体の重複配送（開いたメッセージの正確なリプレイは未読状態を決して再生しない）、バイト同一性のみで証明されるクラッシュコピー照合（バイト長では決してない）、ヘッダのみスキャン（受信者所有 `HeaderInterest`、単調な machine+model 注意統合、`.senv` ペイロード読み取りなし、モデルやネットワーク呼び出しなし）、宣言済みスキャン/オープン予算、バイトオフセット継続カーソルで実際の行パースを束縛する宣言済みスキャン/オープン予算、そして自動昇格しない認証付き inbox→read オープン | 動作 (T-45, T-46)。契約は [D-031](spec/DECISIONS.md) / [D-036](spec/DECISIONS.md) / [D-037](spec/DECISIONS.md) |
| TTL スイープからトゥームストーンへ (T-7, 強化 T-49) | 動作 — 受信者所有の保持（デフォルト 14D、7–30D の範囲、送信者 `TTL` は上限のみ）、受信者ローカルの期限時計（`RECEIVED_AT + effective_ttl`、決して `CREATED` ではない）、deliver/scan/open/recover では決して走らずデーモンもない明示的メンテナンス `sweep_expired`、本文削除の前に公開される `mail/expired/<seat>/<digest>.json` の不変トゥームストーン、`EXPIRED` スキャンスキップ、`ALREADY_EXPIRED` オープン、期限切れ `ENVELOPE_ID` の正確な再配送は `DUPLICATE` のままで何も復活させない。トゥームストーンは自身のファイル名 = `envelope_id` を証明し、`EXPIRED` を主張する前にインデックス行を束縛しなければならない（壊れた/競合するトゥームストーンは `INDEX_BODY_MISSING` を覆い隠せない）、そして一回のメンテナンスパスがすべてのトゥームストーン+BOTH クラッシュ状態を `EXPIRED` に収束させる。契約は [D-038](spec/DECISIONS.md) / [D-039](spec/DECISIONS.md) |
| `saimail.legacy` LEGACY v0 — 正準な不変 LEG1 前任者アカウント、正確な `OpenedEnvelope` ペイロード/K/TOPIC 採用証明、ストア生成の移植不可能な `LegacyEntry`、ドメイン分離されたコンテンツ+トランスポートのエントリ識別、明示的な不変受信者ローカルストア、受信者所有 `received_at` 順の正確な件名検索、観測/新規スコープ、引用参照、不一致、`WATCH_NEXT:UNVERIFIED` を分離したまま保ち権威を作らない、進捗保証付きキーセット後継ページネーション — 権威、タスク、コマンド、プロモーション、KNOWLEDGE を作らない | 動作 (B-013 / T-50、強化 T-51)。契約は [D-040](spec/DECISIONS.md) / [D-041](spec/DECISIONS.md) / [LEGACY v0](spec/04-LEGACY-v0.md) |
| `saimail.sailetter` SAILETTER / `HUMAN_PRIVATE` — 正準 `HLET1` 平文、受信者束縛 `HENV1` コンテナ（P-256 ECDH + HKDF-SHA256 + ChaCha20Poly1305、受信者秘密鍵操作の前に検証される Ed25519 送信者認証）、`NO_IMPLICIT_RECOVERY` 付きの明示的 `STRICT`/`RECOVERABLE` モード、ソフトウェア参照プロバイダを持つ `HumanPrivateKeyProvider` シーム、移植不可能な opened 型状態、平文の `SUBJECT`/`BODY` も意図的な平文永続化も持たない暗号文専用 `human-private` ストア | 動作 (B-001 / T-55)。契約は [D-042](spec/DECISIONS.md) / [SAILETTER v0](spec/05-SAILETTER-v0.md) |
| `saimail.hardware_piv` ハードウェア保管 — 既存の PIV P-256 鍵の上で同じプロバイダシームを満たす `PivP256Provider`、スロット公開鍵から派生する識別、ECDH ごとに一つの明示的セッション（open、オプションの単一 PIN 試行、トークンが強制する touch、close）、正直な `HARDENED` / `COMPATIBLE_WEAK_POLICY` / `UNKNOWN_POLICY` インタラクション分類、正規化された `HARDWARE_*` 拒否、厳密に読み取り専用の検出、何もプロビジョニング・インポート・削除・リセットしない明示的な非破壊 `python -m saimail.hardware_piv verify`。ハードウェアサポートは宣言された `hardware-yubikey` エクストラであり、正準スイートはそれなしで通る | 動作 (T-56)。契約は [D-043](spec/DECISIONS.md) / [hardware custody](spec/06-HUMAN-HARDWARE-v0.md) |
| `saimail.human_attention` HUMAN_ATTENTION_BUDGET v0 — 呼び出し元が供給するルートの下の受信者ローカル注意キュー: キュー時計のみの操作時間、キューが生成する人間識別とエンキュー時刻、不変の候補公開と提示済みレシート公開、アトミックに置換可能なリース、すべての遷移を直列化する一つの OS バックロック、ローリング受信者時間予算（デフォルト `1`/`86400`s、`0` は有効）、受信者エンキュー瞬間より上の決定論的割当優先、二段階 `RESERVE` → `ACK_PRESENTED` 配送と fail-closed 時計退行、クラッシュ順復旧とリース失効、明示的 `release`、そしてデータとして返される延期結果（`DEFERRED` / `ATTENTION_BLOCKED` / `ATTENTION_HALT_REQUIRED`） — 送信者重要度フィールドなし、ペイロード検査なし、モデルやスコアなし、自動状態変異なし、ゼロメッセージは有効な成功 | 動作 (B-011 / T-57、T-58 で修正)。契約は [D-044/D-045](spec/DECISIONS.md) / [HUMAN_ATTENTION_BUDGET v0](spec/07-HUMAN-ATTENTION-v0.md) |
| `saimail.ally_advice` ALLY_ADVICE v0 — observed/unverified-inferred/proposal/counterevidence/uncertainty/agency セクションを分けて持つ、境界付き不変正準 `ALLY1` 私的省察、2 つの観測と 3 つの異なる参照からなる構造フロア、必須の引用付き反証、固定 `RECIPIENT_DECIDES`、移植不可能な証明型を生成する呼び出し元供給の存在リゾルバ（意味的支援は主張しない）。公式アダプタは無変更の HLET1/HENV1 と暗号文専用 `HumanPrivateStore` を再利用し、受信者注意アクセプタンスは明示的 `HUMAN_PRIVATE` + `LETTER_ID` のままで、ゼロ助言も有効 | 動作 (B-012 / T-59)。契約は [D-046](spec/DECISIONS.md) / [ALLY_ADVICE v0](spec/08-ALLY-ADVICE-v0.md) |
| `saimail.ally_generation` ALLY_ADVICE GENERATION v0 — B-012 の上に置かれた境界付き自律生成ゲート: 明示的な呼び出し元供給の `ReflectionCorpus`（履歴発見なし、project-operational ソースドメイン、64 項目 / 項目あたり 8192 バイト / 合計 131072、決定論的なドメイン分離コーパス識別）、閉じたジェネレータ結果（`NO_ADVICE`、または refs がコーパス内に存在しなければならない一つの既に有効な `AllyAdvice`）、再試行や書き直しループなしで実行ごとに最大一つのジェネレータ呼び出しと一つのレビュア呼び出し、完全なコーパスを受け取りジェネレータの推論を一切受け取らない独立した意味レビュア、fail-closed な全 `PASS` 承認付きの 8 つの `PASS`/`FAIL`/`UNKNOWN` 次元（`OBSERVATION_SUPPORT`、`COUNTEREVIDENCE_ADEQUACY`、`SCOPE_DISCIPLINE`、`NO_MOTIVE_INFERENCE`、`NO_FLATTERY`、`NO_COMPLIANCE_PRESSURE`、`UNCERTAINTY_ADEQUACY`、`RECIPIENT_AGENCY`）、呼び出しに束縛されたミント（呼び出し元が構築したレポートはデータであって証明ではない: 実際の一回の `reviewer.review` 呼び出しが譲渡不可能な `ReviewInvocationResult` をミントし、その証明だけが承認されうる）、`OBSERVATION_SUPPORT` / `COUNTEREVIDENCE_ADEQUACY` の `PASS` には少なくとも一つのコーパス ref の引用が必要、正確な候補 + 正確なコーパス + ルーブリックに束縛された譲渡不可能な `SemanticallyReviewedAllyAdvice` 証明、無変更の HLET1/HENV1 回廊を再利用する生成済みプライベートアダプタ。すべてのコーパス項目は `EVIDENCE_REF` とは区別された、呼び出し元宣言の `EVENT_REF` も運び、それはコーパス識別に束縛される。自律生成された反復パターンの助言は、レビュアが起動される前に、少なくとも二つの異なる宣言イベントにまたがる OBSERVED 証拠を引用しなければならない（`ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS`、レビュア呼び出しゼロ。`EVENT_REF` は主張であって真実ではなく、自動的に推論されることはない）。承認は決して封印・保存・注意アクセプタンスを行わず、ゼロ助言は成功した非配送のままとどまる | 動作 (B-016 / T-61、T-62 と T-66 で修正)。契約は [D-047/D-048/D-049](spec/DECISIONS.md) / [ALLY_ADVICE GENERATION v0](spec/09-ALLY-GENERATION-v0.md) |
| `saimail.project_corpus` PROJECT CORPUS v0 — B-016 の上に置かれた境界付き実プロジェクトコーパスビルダ: 一つの明示的な呼び出し元供給 `ProjectCorpusRequest`（正準な `project:` スコープ、正確な半開区間 UTC 選択ウィンドウ、固定 `EXPLICIT_BOUNDED_SET` 基盤、凍結された 7 種の `PROJECT_OPERATIONAL` ソース語彙、64/8192/131072 の上限）、ゼロディスカバリ（ディレクトリ、リポジトリ、SAIPEN、ネットワーク、モデルへのアクセスなし、パス引数なし）、スコープ + ソース種別 + ソース ref + コンテンツダイジェストからビルダがミントするドメイン分離された `EVIDENCE_REF`（観測時刻がそれを変えることはない）、正確な呼び出し元宣言からビルダがミントする `EVENT_REF`（宣言メンバーは証拠 ref にすぎない。チケット ID、ファイル名、パス、タイムスタンプ、同一テキストがグループ化やマージを行うことはない）、正確なパーティション要件（未知のメンバー、未割り当て成果物、複数イベント成果物、空イベントは拒否）、不変の B-016 `CORPUS_ID` の隣にポリシー + スコープ + ウィンドウ + 成果物 + グルーピングを束縛する `BUILD_ID`、譲渡不可能な `BuiltProjectCorpus` 証明（直接構築と `dataclasses.replace` は拒否。コーパス、グルーピング、ウィンドウ、成果物集合の変化は拒否）と将来の実プロジェクトパイロット向け `require_built_project_corpus` ゲート。選択の完全性は `NOT_PROVEN` のままで、コーパス平文は永続化されず、汎用 B-016 と手動 B-012 の経路は不変 | 動作 (B-017 / T-67)。契約は [D-050](spec/DECISIONS.md) / [PROJECT CORPUS v0](spec/10-PROJECT-CORPUS-v0.md) |
| `lab/project_corpus_pilot.py` B-018 実プロジェクトコーパスパイロット — コーパスが一つもビルドされる前に一度だけ凍結される、オペレータ承認の不変登録（`MARKDOWN_SECTION` / `LOG_RECORD` / `WHOLE_FILE` セレクタ付きの 8 つの正確な成果物、5 つの明示的イベント宣言、ソースごと・コンテンツごとの SHA-256 ピン）。登録されたパスだけを読み、登録されたセレクタだけを抽出し、ピンの不一致には fail-closed する読み取り専用キャプチャアダプタ（唯一の狭い例外は追記専用ジャーナルソースで、その登録済み全レコードは凍結されたコンテンツピンを証明し `APPEND_ONLY_SOURCE_MATCHES_REGISTERED_CONTENT_PINS` として記録される）。ビルドは不変の B-017 ビルダだけを通る。正確な `EVIDENCE_REF`/`EVENT_REF` マップ、境界付きミューテーション、モデルなし・メールなしの証明付きの、一つのラボスナップショットとレポート。生の `ReflectionCorpus` は依然として将来のパイロット証明ゲートに失敗する | 動作 (B-018 / T-68)。登録は [lab/project_corpus_pilot_registration.json](lab/project_corpus_pilot_registration.json) |
| `lab/project_corpus_generation_pilot.py` B-019 実プロジェクト境界付き生成パイロット — ディスカバリー前に一度凍結される不変のライブ登録（正確な B-018 の `REGISTRATION_ID`/`BUILD_ID`/`CORPUS_ID` を束縛、8 ディスカバリー + 2 生成 + 2 レビュー <= 12 ライブ呼び出し、ローカルの生出力/プロンプト永続化なし、プロバイダ側保持は `NOT_VERIFIED_BY_SAIMAIL`）。ランナーは不変の B-018/B-017 経路で正確な B-018 `BuiltProjectCorpus` を再ビルドし、モデル呼び出しの前に同一性の差異に対して `NO_GO_INPUT_DRIFT` で拒否する。生の `ReflectionCorpus` は依然として `PROJECT_CORPUS_BUILDER_PROOF_REQUIRED` で失敗する。機密情報を除去したディスパッチが永続的な呼び出し記録をメタデータ専用に保ち（プロンプト/出力/エラーはパース前に `finally` ブロックで null 化）、2 つの役割交換レプリケートが不変の B-016 `generate_reviewed_ally_advice` を通り、再試行なし・修復プロンプトなし・凍結後置換なし。成果物/レポート/解釈は識別、ハッシュ、長さ、証拠 ref、次元判定、カウントだけを運ぶ — プロンプトテキスト、コーパス内容、候補散文、レビュアの根拠、プロバイダのエラー本体は決して運ばない（母集団セクションは明示的にサニタイズされた投影から構築され、歴史的な T-69 の主張は加算的に修正された — [lab/analysis/project_corpus_generation_20260919T220641Z_privacy_correction.md](lab/analysis/project_corpus_generation_20260919T220641Z_privacy_correction.md) 参照）。登録された一回のライブ実行は 8 呼び出し（ディスカバリー 6、生成 2、レビュー 0）を使い、レビュア呼び出しゼロ、メール/注意の副作用ゼロ、オペレータ提示なしで `ERROR`（R1、パース不能なジェネレータ回答）と `NO_ADVICE`（R2）を生成した | 動作 (B-019 / T-69)。登録は [lab/project_corpus_generation_registration.json](lab/project_corpus_generation_registration.json) |

直近のベンチマーク判定、否定的発見、推奨される次の単純化は
[bench/ANALYSIS.md](bench/ANALYSIS.md) にある。下流で何かをビルドする前に読むこと。

## 実行方法

```
pip install -e ".[test]"
python -m pytest -q
python bench/t9b.py --out bench/out
python bench/r1_shootout.py --out bench/out
python bench/selector_run.py --out bench/out
python lab/saifren_run.py --out lab/out --dry-run
python lab/stability_run.py --out lab/out --dry-run
python lab/project_corpus_pilot.py --register   # frozen once, before any capture
python lab/project_corpus_pilot.py --run
python lab/project_corpus_generation_pilot.py --register   # frozen once, before any live call
python lab/project_corpus_generation_pilot.py --dry-run
python lab/project_corpus_generation_pilot.py --run        # one registered live run
python tools/fg05_local_scenario.py                       # FG-05 offline end-to-end scenario
```

上記のどれもネットワークに触れない。ライブ `lab/` 実行は触れ、以下の認証情報を必要とする。

## ローカルで試す

インストール可能な一つのオフラインコマンドが、エンドツーエンドのデモとユーティリティベンチマークを実行する:

```
pip install "saimail[crypto]"     # runtime crypto extra the demo needs
saimail-local --version           # version + result schema identities
saimail-local                     # FG-05 two-participant demo (default)
saimail-local --utility           # FG-06 TOTAL_FRICTION benchmark
saimail-local --api-map           # path to the machine-readable stable API map
saimail-local --out OUT --json    # bounded machine-readable result
```

デモ実行は、すべてのアクセプタンス不変条件が成立する場合にのみ `0` で終了し、境界付きの状態サマリを印字する。一時ワークスペースは OS の一時ディレクトリの下に置かれ、`--keep` が与えられない限り削除される。`--out DIR` は `local_scenario_result.json` と `fg06_utility_result.json` を書く。安定した API マップは `lab/stable_local_api.json` にある。制限と明示的な「約束しない」リストは [spec/16-UTILITY-AND-LOCAL-ENTRYPOINT-v0.md](spec/16-UTILITY-AND-LOCAL-ENTRYPOINT-v0.md) にある。デモとベンチマークはネットワーク呼び出しゼロ、モデル呼び出しゼロ。SAIMAIL は自動的な真実検出、レビュアの信頼性、プロバイダの JSON Schema 強制、自動プロモーションや自動通信、Gmail/Slack/Outlook 統合、ハードウェアキーのプロビジョニング、ゼロのプロトコルオーバーヘッドを**約束しない**。

### 永続ローカルワークスペース (V2-01)

実用的なローカルワークフロー。二つのワークスペース、二つの永続的識別、別々のプロセス起動にまたがる一つの実ローカルメッセージ:

```
pip install "saimail[crypto]"
saimail-local init --workspace ws-a --seat SAIMAIL-A
saimail-local init --workspace ws-b --seat SAIMAIL-B
saimail-local identity --workspace ws-a --export-card a.card.json
saimail-local identity --workspace ws-b --export-card b.card.json
# exchange the PUBLIC cards and register each side (one command each)
saimail-local recipient add --workspace ws-a --alias bob --card b.card.json --peer-workspace ws-b
saimail-local recipient add --workspace ws-b --alias alice --card a.card.json --peer-workspace ws-a
# every command below is its own process; state persists on disk
saimail-local send --workspace ws-a --to bob --claim "one line for bob"
saimail-local inbox --workspace ws-b            # metadata only, no payload
saimail-local open --workspace ws-b --envelope sha256:...
saimail-local reopen --workspace ws-b --envelope sha256:... # re-read opened message without state mutation
saimail-local send --workspace ws-a --redeliver sha256:...   # exact replay -> DUPLICATE
saimail-local acceptance --root fresh-dir       # one-command PASS/FAIL harness
```

識別は再起動を生き延びる: `saimail-local identity` は何回の別々の起動の後でも同じ公開フィンガープリントを返す。正確な配送の繰り返しは正準な `DUPLICATE` であり（元の `RECEIVED_AT` が保たれ、二つ目の未読メッセージは現れない）— CLI 自身はいかなる重複排除レイヤーも追加しない。`open` は正確なメッセージ識別を要求し、それを読み取り状態へ動かし、決してプロモートしない。`reopen` は、セッション間で既に読んだメッセージを永続状態を変異させずバンドルを複製せず、受信者が明示的に再読み込みできるようにする。プロモーションは別個のアクションのままである。機械可読な結果はコマンドごとに `LOCAL_WORKSPACE_COMMAND_1`、ハーネスは `LOCAL_WORKSPACE_RESULT_1`。`--json` はすべてのコマンドで動く。

ローカルファイルシステム専用: 配送は受信者のワークスペースへの明示的なパスなので、送信者はそれへの書き込みアクセスを必要とする。Gmail/Slack/Outlook なし、アダプタなし、サーバやデーモンなし、リモートサービスなし、意味レビュアなし、自律通信なし、ハードウェアキープロビジョニングなし。

### ローカルアルファ候補 (0.0.2a3)

ネットワーク依存なしで完全な永続ワークスペースワークフローをテストするための、凍結済みローカル証明済みアルファ候補:

```
pip install "saimail-0.0.2a3-py3-none-any.whl[crypto]"
saimail-local --version
```

候補マニフェストは、正確なパッケージ識別、コンテンツ証明、モードに即したセキュリティ制限、リリースツールの真態（歴史的 a1 バンドルへのビルド拒否と、凍結済み候補への上書き拒否）を記録する。`tools/local_alpha_release.py
verify --bundle <dir>` は記録済みハッシュを再検査し、ホイールコンテンツ証明は保管モジュール、識別スキーマ v2、`--custody`/`custody status`/`custody migrate` 表面、初回実行通知がない候補を拒否する。さらに `--require-product-delta` には P1/V4-01/V5-01 の製品表面を必要とする。破損したホイールや破損した記録済みハッシュは拒否される（レッドコントロール）。リリースプライバシースキャン（`tools/scan_local_alpha_privacy.py`）は植え付けられたマーカーや植え付けた鍵材料で失敗する。歴史的 a2 の証拠は `release/evidence/a2/` にある。現在の候補固有の証拠（インストール済みホイール検証、Windows os-store 証明、マイグレーション証明、再現性、プライバシー/完全性レッドコントロール、クレームマトリクス、ゲート評価）は `release/evidence/a3/` にある。完全な契約、アルファスコープ、プラットフォーム証明スコープ（win32 上の CPython 3.11）、「主張しない」リストは [spec/18-LOCAL-ALPHA-v0.md](spec/18-LOCAL-ALPHA-v0.md)、[spec/20-LOCAL-KEY-CUSTODY-v0.md](spec/20-LOCAL-KEY-CUSTODY-v0.md)、[spec/DECISIONS-D055.md](spec/DECISIONS-D055.md)、[spec/DECISIONS-D056.md](spec/DECISIONS-D056.md) にある。

**動作する:** パッケージのインストール; 永続ワークスペースの初期化; 公開識別カードの交換; 既知ローカルピアの登録; ローカル送信; 受信箱一覧（メタデータのみ）と境界付き受信箱クエリ/トリアージ（`P1`); 明示的オープン; 明示的な一ホップの通信継続（`V4-01`); 重複抑制; 再起動永続性; オプションのデスクトップローカルメッセンジャー GUI（`V5-01`、`saimail-gui`、基本依存ではない `gui` エクストラ配下の PySide6）; raw（デフォルト）識別保管; 検証済み OS 認証情報バックエンドが存在する場所での明示的な `os-store` 保護保管（フィンガープリント保存マイグレーションを含む）; FG-05 デモ; FG-06 ベンチマーク; V2-01 アクセプタンス; 機械可読結果。

**存在しない:** リモート配送、メールプロバイダ統合、サーバ、デーモン、アカウント同期、自動受信者発見、保護されたデフォルト、ハードウェア保管、鍵ローテーション、自動リカバリ、自動通信、汎用セキュアメッセンジャー。

**保管警告（二つのモード）:** デフォルトの `raw` モードは秘密の Ed25519/X25519 識別鍵をワークスペース内の生ソフトウェアファイルとして保存する — **保存時暗号化なし**、そしてコピーされたワークスペースディレクトリは識別をコピーする。明示的な `os-store` オプトインは秘密鍵を OS 認証情報ストアへ移し、生バイトをワークスペースから取り除き、ワークスペースディレクトリコピー露出**のみ**から保護する。マルウェアや同じ権限ユーザとして動くプロセス、管理者/カーネル侵害、ハードウェア攻撃、物理的接近、人間の識別証明からは保護**しない**。ハードウェア保管、ローテーション、自動リカバリは提供しない。OS アカウント/ホストのマイグレーションは鍵材料を孤立させるかもしれず、この候補のバックエンド証明は Windows 固有（`WinVaultKeyring`）。主張の境界: [spec/20-LOCAL-KEY-CUSTODY-v0.md](spec/20-LOCAL-KEY-CUSTODY-v0.md)。

**ユーティリティ警告:** 測定された判定は `UTILITY_CONDITIONAL`。SAIMAIL はトークンやコストを普遍的に節約するわけではなく、中/高開封率ワークロードは宣言された摩擦モデルの下で中立である。

**アルファ警告:** これはスコープされたローカルアルファ候補であって、本番通信サービスではない。

**公開状態:** 候補をビルドすることはパッケージが公開されたことを意味しない。`publication_status = NOT_PUBLISHED`。公開は別個の明示的なオペレータアクションである。正確な `0.0.2a2` ホイールは真に分離された Linux / Python 3.13.5 環境で外部証明済み（`release/evidence/a2/external_linux_verification.json`）。現在の `0.0.2a3` ホイールはローカルで凍結・証明済みだが、その真の外部証明はまだ受理されていない（`READY_FOR_EXTERNAL_INSTALL_PROOF`）。a2 の外部証明が継承されることはない。公開承認（G17）は依然として ABSENT。

## 手紙を書く価値があるとき

SAIMAIL は特別な郵便局であり、二つ目のチャットではない。手紙はオペレータのタイトルバーに届いて割り込む。チャットはエージェントが一日中オペレータと話す場所である。したがってデフォルトはチャットであり、手紙は例外である。

**両方**の条件を同時に満たすときだけ手紙を書く:

1. オペレータはチャットを読んでいない可能性が高い（無人実行であるか、エージェントが恒久的に停止しようとしている）、かつ
2. オペレータが行わなければならない、または決定しなければならないことが変わる: 彼らだけが解除できるハードストップ、データや現金を失うリスク、あるいは他のプロジェクトを変える発見。

次のようなことのために手紙は書かない: 完了したチケットや Work、テストやゲートの結果、要約や最終報告、エージェントがすでにチャットで言ったこと、チャット回答が列挙している手動チェックの催促、進捗、あるいはエージェントがチャットで質問できる質問。送信する前に、エージェントは一行のチャットでチャットでは足りない理由を述べる; できなければ送信しない。一つの決定につき手紙は高々一回: 繰り返しも、内容を言い直す追伸もいけない。

記録のために、送るべきでなかった手紙が二通ある (2026-09-29): 「T-258 fixed, gates 2316 passed, run these commands」と「T-21 closed as release candidate, one manual check pending」。どちらも完成報告であり、その内容のすべてはエージェントのチャット回答の中にあった。ZAICODE のエージェントプロンプトはいま上記の規則を述べており、`saimail-local send --help` もそれを繰り返す。その背後にある考えはツールより古い (`idea_letters.md`): 予期しない場所は許されるが、予期しない中断は高くつく。

## SAIRoute 認証情報

一つの論理ハンドル。人間が一度プロビジョニングし、その後は誰も鍵を貼ることなくすべてのエージェントが解決する:

```
credential://9router/sairoute
```

ローカル認証情報ストアを通じて解決される — Windows では Windows Credential Manager であり、コードは `keyring` がインポートが成功したからという理由で仮定するのではなく、実際に `WinVaultKeyring` を選択したことを検査する。そのストアになりえない keyring のホストは、動作しているように見える代わりに `SAIROUTE_CREDENTIAL_BACKEND_UNSUITABLE` で失敗する。

```
python tools/provision_sairoute_credential.py               # store it, once
python tools/provision_sairoute_credential.py --check       # stored? which backend?
python tools/provision_sairoute_credential.py               # again = rotation
python tools/provision_sairoute_credential.py --delete      # remove it
python lab/saifren_run.py --out lab/out                     # the ordinary live run
```

秘密は対話式のエコーしないプロンプトで入力され、一度確認される。`--key` も `--secret` も標準入力経路もない: `echo SECRET |` は認証情報をシェル履歴に置く。それこそがこのストアが取り除くために存在する露出である。TTY なしではツールは `SAIROUTE_PROVISIONING_REQUIRES_TTY` で拒否する。

**通常のライブコマンドは環境から秘密を読まない**（D-019）。欠落した認証情報は `SAIROUTE_CREDENTIAL_NOT_PROVISIONED` であって、静かなフォールスルーではない。古い `SAIROUTE_API_KEY` 変数は依然として動くが、名前が指定された場合のみ:

```
python lab/saifren_run.py --out lab/out --credential-source env
```

その選択は成果物に `credential.source` として記録される。従ってレガシー変数を使った実行はそう言う。成果物、レポート、ログ行、例外が値そのものを運ぶことは決してない。

依存関係は [pyproject.toml](pyproject.toml) で宣言される。ライブラリ自体には依存がない: パーサはデータ専用である。`test` エクストラはフルスイートが必要とするすべて（トークナイザを含む）をインストールする — 一つの契約。従って告知されたコマンドは動作するコマンドである。`tiktoken` はピン留めされ、公開されるトークン比率は再現可能なままである。初回使用時に小さな BPE テーブルをダウンロードする。モデル重みは決してダウンロードしない。

ハードウェア保管は別個のオプションエクストラであり、実行時にインストールされることは決してない:

```
pip install -e ".[hardware-yubikey]"
python -m saimail.hardware_piv inspect          # strictly read-only
python -m saimail.hardware_piv verify --device NAME --slot 9D
```

エクストラなしでは、すべてのハードウェアエントリポイントは `HARDWARE_PROVIDER_UNAVAILABLE` で拒否する。エクストラありでもトークンなしでは、手動検証は `NOT_RUN_NO_HARDWARE` と報告され、`PASS` でも `FAIL` でもない。両コマンドは非破壊的である: プロビジョニング、インポート、削除、リセットの経路はなく、自動スロット選択もなく、`--pin` オプションもない — PIN は対話式プロンプトでのみ入力される。

## 文書

| ファイル | 内容 |
|---|---|
| [idea.md](idea.md) | 創設ソース。レシート `SRC-003` として逐語的にキャプチャ（`SRC-001` を修正） |
| [idea_continue1.md](idea_continue1.md) | 継続ソース。`SRC-004` としてキャプチャ（`SRC-002` を修正）。キャプチャ時の名前は `idea_continue.md` |
| [idea_continue2.md](idea_continue2.md) | その後の継続。レシートとしてはキャプチャされていない |
| [idea_letters.md](idea_letters.md) | 手紙に関するメモ。レシートとしてはキャプチャされていない |
| [spec/BACKLOG.md](spec/BACKLOG.md) | まだビルドされていないソース要件。それぞれが自身のレシートを引用 |
| [spec/DECISIONS.md](spec/DECISIONS.md) | 派生仕様へのすべての修正とその理由 — 後の権威 |
| [spec/00-PRINCIPLES.md](spec/00-PRINCIPLES.md) | 認識論的ゼロトラスト、ステートメント種別、証拠グレーディング、スチュワード役割 |
| [spec/01-SAILANG-v0.md](spec/01-SAILANG-v0.md) | 主張レコード: フィールド、閉じた集合、ラングゲート、トリアージフレーム |
| [spec/02-SAIENVELOPE-v0.md](spec/02-SAIENVELOPE-v0.md) | `.senv` コンテナ、暗号、五つの不変条件、SAINOTE |
| [spec/03-POST-OFFICE.md](spec/03-POST-OFFICE.md) | レイアウト、関心フィルタ、三つの記憶層、プロモーション |
| [spec/04-SAIPEN-SEAM.md](spec/04-SAIPEN-SEAM.md) | SAIPEN が既に実装しているもの、本当に新しいもの、統合経路 |
| [spec/07-HUMAN-ATTENTION-v0.md](spec/07-HUMAN-ATTENTION-v0.md) | 受信者所有の人間注意予算: 候補識別、ローリングウィンドウ、リザーブ後 ACK 配送、延期結果、プライバシーと権威の境界 |
| [spec/15-LOCAL-SCENARIO-v0.md](spec/15-LOCAL-SCENARIO-v0.md) | FG-05 二参加者オフラインシナリオとその機械可読な `LOCAL_SCENARIO_RESULT_1` 結果 |
| [spec/16-UTILITY-AND-LOCAL-ENTRYPOINT-v0.md](spec/16-UTILITY-AND-LOCAL-ENTRYPOINT-v0.md) | FG-06 TOTAL_FRICTION ベンチマーク、公正ベースライン境界、ローカルエントリポイント、安定した API/型/失敗マップ、「約束しない」リスト |
| [spec/17-LOCAL-WORKSPACE-v0.md](spec/17-LOCAL-WORKSPACE-v0.md) | V2-01 永続ローカルワークスペース契約: レイアウト、コマンド、識別カード、ローカル配送境界、`LOCAL_WORKSPACE_COMMAND_1` / `LOCAL_WORKSPACE_RESULT_1`、プライバシー/アトミック性と正直な制限 |
| [spec/18-LOCAL-ALPHA-v0.md](spec/18-LOCAL-ALPHA-v0.md) | ローカルアルファ候補契約: スコープ、バンドルレイアウト、マニフェスト、スタンドアロン検証器、完全性/プライバシーゲート、公開境界 |
| [spec/20-LOCAL-KEY-CUSTODY-v0.md](spec/20-LOCAL-KEY-CUSTODY-v0.md) | V3-01 保管脅威モデル、選択された OS ストアオプション、識別スキーマ v2 ハンドル契約、マイグレーション順序、名前付き `CUSTODY_*` 失敗、主張の境界 |
| [spec/22-LOCAL-INBOX-QUERY-v0.md](spec/22-LOCAL-INBOX-QUERY-v0.md) | P1 メタデータ専用受信箱トリアージクエリ: 正確な AND フィルタ、`received_at` 時間境界、宣言されたスキャン予算、バイトオフセット継続カーソル、fail-closed 状態、ペイロードなし証明 |
| [spec/26-SAITELEMES-v0.md](spec/26-SAITELEMES-v0.md) | SAITELEMES v0: 実行中エージェント間の一呼び出しテレグラム、活動席ガード、ヘッダー専用ターン開始時読み取り |
| [spec/24-LOCAL-CORRESPONDENCE-CONTINUATION-v0.md](spec/24-LOCAL-CORRESPONDENCE-CONTINUATION-v0.md) | V4-01 一ホップ返信: 二つの関係ドメイン（SENV2 `REF` トランスポートリンク対 SAILANG `SUPPORTS`/`REFUTES`/`CON`）、READ 前提条件、識別束縛受信者解決、結果契約 |
| [bench/ANALYSIS.md](bench/ANALYSIS.md) | 測定が実際に何を意味するか。否定的発見を含む |
| [lab/LATEST.md](lab/LATEST.md) | ライブ実行インデックス: どの実行が現行か、および `lab/analysis/` の各自の不変な読み解きを持つすべての過去の実行 |
| [provenance/RECEIPT_KIND_SCOPE.json](provenance/RECEIPT_KIND_SCOPE.json) | レシートの intake 種別はトランスポートであり、そのセグメントは作者性であるという規則 (D-017) |
| [provenance/quarantine/SRC-007.json](provenance/quarantine/SRC-007.json) | `SRC-007` の隔離レコード: 元のダイジェスト、理由、その無害化派生物 (D-023) |
| [spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md](spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md) | SAIPEN 自身のエクスポートが隔離済み本文を残せるようになる前に SAIPEN Core が必要とするもの |

コードを書く前に `04-SAIPEN-SEAM.md` を読むこと。ここで説明された真理レイヤーの大部分は、人間の意図のために SAIPEN 内で既に動いている。SAIMAIL はそれを再構築するのではなく、エージェント間メールへ一般化する。

## 荷重を支える規則

- **`message != memory`.** 永続記憶にはプロモーションが必要であり、プロモーションは種別を認識する: 事実と観測には証拠、仮説には反証条件、ゴールと価値には出所だけ。
- **情報的であって憲法的ではない。** プライベートメッセージは何でも言え、何も承認しない。コマンドに見えるペイロードテキストは不活性である。
- **観測可能だがプライベート。** 内容は封印できる。トラフィックは決して封印されない。
- **意図主張なし。** ステートメントについての最も強い判定は `CONTRADICTED` である。人についての判定は存在しない。
- **レコードが権威である。** トリアージフレームはデコード可能だが、決して権威ではなく、決して証拠ではなく、省略したものを再構成しない。

## 権威の所在

```
AUTHORITATIVE RECEIPT LINEAGE > DERIVED SPEC > IMPLEMENTATION > TESTS
```

`idea.md` と `idea_continue1.md`（当時の名前は `idea_continue.md`）がレシートである（`.saipen/intake/active/SRC-003.md`、`SRC-004.md`。`SRC-001`/`SRC-002` は本文ではなくファイルパスを記録したキャプチャミスであり、書き直される代わりに修正済み原文として保たれている）。`spec/` の下のすべては派生解釈であり改訂されうる。`spec/DECISIONS.md` はすべての改訂とその理由を記録する。仕様がレシートと不一致のとき、レシートが勝つ。

<!-- source-digest: README.md sha256:b66f070aab6b5f11 -->
