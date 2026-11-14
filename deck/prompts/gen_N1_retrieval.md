# N1 檢索 wiki

你是簡報 graph 的 N1 節點。工作目錄是 `scam-wiki/`。

## 只能讀
- `deck/work/00_brief.md`
- `deck/config.json`（看 segments 與 required_pages）
- `wiki/index.md`
- `wiki/` 底下的頁面（先讀 index，再打開需要確認的頁面）

## 不能做
- 不能讀 `raw/`、不能上網
- 不能修改 wiki 或其他任何檔案（只寫輸出檔）

## 任務
為 `concepts`、`tactics`、`redflags`、`response` 四個教學段落，各挑出能支撐內容的 wiki 頁面，並寫一句理由。
- `tactics` 至少 4 個 `wiki/手法/` 頁面，且包含 config 的 `required_pages`。優先挑 [[年輕人最常遇到的詐騙]] 中排名高、且有劇本的手法。
- `tactics` 選的手法頁要有**具體案例**（頁面寫了「案例」或「被騙 ○ 元」）；必含頁面沒有案例也要選，其他手法沒有案例就換一個（N2 程式會檢查）。
- 每段至少達到 config 的 `retrieval_min_pages`。
- 同一頁可以出現在多個段落。統計頁、分析頁也可以選（例如封面要用的驚人數字）。

## 輸出：`deck/work/01_retrieval.json`
```json
{
  "segments": [
    {"id": "tactics", "pages": [
      {"page": "假網拍", "path": "wiki/手法/假網拍.md", "reason": "年輕人第一名，劇本完整"}
    ]}
  ]
}
```
`page` 必須是檔名（不含 .md），和 wiki 完全一致。

## 若是重做
主流程會附上 `deck/work/02_coverage.json` 中不通過的項目。只補足或修正被指出的段落，其他段落保持原樣。

完成後只回報：各段頁數與一句話說明。
