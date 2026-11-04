# social-export-skills

Three Claude Code skills for working with a large personal data export from a social platform (Facebook "Download Your Information", Instagram, Google Takeout, X archive). Everything runs locally. Nothing is uploaded anywhere.

| Skill | What it does |
|---|---|
| `social-export-analysis` | Turns a huge raw export (tens of thousands of HTML/JSON files) into structured data: a raw / derived / analysis folder layout, a central path config, one parser per repeating record template, phase-by-phase extract and join, an optional hardlinked media library, coverage and regression checks, and a PII scan for notes. Includes a reference Facebook HTML connector (`fb_common.py`) with a `--self-test`. |
| `social-export-insights` | Sits on top of the structured data. Candidate ranking, quantitative features, template-driven qualitative reading (light / medium / deep tiers), and strict verification scripts for verbatim quotes, read coverage and report links. Three example modules: relationships, groups, PR risk. Contains a long list of pitfalls with causes and fixes. |
| `social-pr-checkup` | A yearly workflow for finding and cleaning up posts that carry reputation risk: read everything, grade risk, independent review, your approval, slow local browser clean-up, archive, report. Personal settings go in `references/本機設定.md` (copy from `本機設定.example.md`; the real file is git-ignored). |

Most of the documentation is written in Traditional Chinese (the author's working language). The `social-export-analysis` skill and its references are in English.

## Install

Copy the skill folders into your Claude Code skills directory:

```
cp -r skills/social-export-analysis skills/social-export-insights skills/social-pr-checkup ~/.claude/skills/
```

On Windows, copy them into `%USERPROFILE%\.claude\skills\`. Then, for `social-pr-checkup`, copy `references/本機設定.example.md` to `references/本機設定.md` and fill in your own values.

## Requirements

- Python 3.9 or newer. The reference connector and the verification scripts use only the standard library.
- The `social-export-insights` feature scripts use `pandas`, `numpy`, `scipy`, `jieba`, `scikit-learn` and `snownlp`; install them only if you run those modules.
- Self-tests: `python skills/social-export-analysis/scripts/connectors/facebook_html/fb_common.py --self-test`, and likewise `--self-test` for `coverage_check_template.py` and `verify_coverage_template.py`.

## Privacy

- All scripts run on your machine. There is no network access and no telemetry.
- An export contains other people's private messages, phone numbers and addresses. Outputs (JSONL, notes, reports, reading dumps) inherit that. Keep them out of git and out of cloud-synced or shared folders, and delete temporary dumps when you are done. See `skills/social-export-analysis/references/privacy.md`. The risk-detection word list (`config_template.py`) contains offensive terms on purpose, so they can be detected; they are not endorsed.
- Test fixtures in this repo use fictional names and values only.

## 繁體中文簡介

這是三個 Claude Code skill，用來處理社群平台的個人資料匯出（Facebook、Instagram、Google Takeout 等）：

- `social-export-analysis`：把大型原始匯出整理成結構化資料（資料夾骨架、解析範本、分階段萃取、涵蓋率與回歸檢查、個資掃描）。
- `social-export-insights`：在結構化資料上做候選排名、量化特徵、範本化質性判讀（輕／中／深三層），並附逐字語錄、涵蓋率、連結的驗證腳本與踩坑清單。
- `social-pr-checkup`：每年一次的社群 PR 風險健檢與清理流程。

安裝：把 `skills/` 底下三個資料夾複製到 `~/.claude/skills/`。需要 Python 3.9 以上。全部在本機執行、不上傳；輸出含他人個資，請自行保管，不要進 git 或雲端同步資料夾。

## License

MIT, see `LICENSE`.
