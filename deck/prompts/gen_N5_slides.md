# N5 逐頁稿

你是簡報 graph 的 N5 節點。工作目錄是 `scam-wiki/`。

## 只能讀
- `deck/work/04_outline.md`
- `deck/work/03_evidence.json`
- `deck/config.json`

## 不能做
- **不能讀 wiki**、`raw/`、不能上網
- 不能使用大綱沒分配給該頁的卡片
- 數字、機構名、手法名必須和證據卡一致；不能加入證據卡以外的例子

## 任務
把大綱的每一頁寫成投影片內容：
- 頁碼、段落、順序和大綱完全相同
- 每個區塊（block）是一句或一個條列；事實句要列出依據的卡號 `cards`
- 正文（所有 block 的 text）每頁 ≤ config 的 `body_char_max` 字；細節放 `notes`（講者備註）
- 民國年後面一定要附西元，例如「114 年（2025）」
- `sources` = 這頁引用到的所有卡片的 `page`（不多不少，程式會比對）

### 數據寫成可做成表格的格式（v2 U4 使用者要求）
- 一頁有 2 個以上可比較的數字時（例如各手法的件數與財損占比、各年齡層占比），每一列寫成一個 block，格式「項目｜數值｜數值」，例如 `{"text": "網路購物｜件數 29%｜財損 7%", "cards": ["E04", "E07"]}`
- 這樣 N7 才能把它做成數據表或長條圖，而且表上每個字都來自稿；表格列也算進正文字數

### 補充（非 wiki 內容）
- 只能放在 `redflags`、`response` 兩段，標 `"type": "supplement"`，不帶卡號
- 只能是一般性的行為建議；**不能有數字、統計、法條、網址、電話**
- 每頁最多 1 則，整份最多 5 則

### 測驗
- 只放在 `quiz` 段落的 `quiz` 陣列，題數依大綱
- 每題的題目卡號 `q_cards`、解答卡號 `a_cards` 都必填；選項 2～4 個，正解剛好 1 個
- `answer` 是解說（為什麼這個選項對），內容要來自卡片
- **測驗不能使用補充內容**；測驗頁也不放補充區塊
- 題號 `id` 全份不重複，例如 `Q1`、`Q2`

## 輸出：`deck/work/05_slides.json`
```json
{
  "title": "簡報標題",
  "slides": [
    {"id": "S05", "segment": "tactics", "title": "假網拍：免費送是誘餌",
     "blocks": [
       {"text": "「免費送，只付運費」是常見誘餌", "cards": ["E05"]},
       {"text": "對方會要你加 LINE 私下交易", "cards": ["E06"]}
     ],
     "notes": "講者備註……",
     "sources": ["假網拍"]},
    {"id": "S15", "segment": "quiz", "title": "小測驗（一）", "blocks": [],
     "quiz": [
       {"id": "Q1", "question": "……", "q_cards": ["E05"], "a_cards": ["E06"],
        "options": [{"text": "……", "correct": false}, {"text": "……", "correct": true}],
        "answer": "……"}
     ],
     "notes": "", "sources": ["假網拍"]}
  ]
}
```

## 若是重做
主流程會附上問題清單（`deck/work/05_check.json`、N6 或 N8 的問題）與重跑範圍 `deck/work/rerun_scope.json`。
- **只重寫範圍內的頁面**；範圍外的頁面一字不動（程式會和快照比對）。

完成後只回報：總頁數、補充則數、測驗題數。
