**🌐 在线阅读 · Live site：<https://pasbean61.github.io/daybreak-brief/>**

# Daybreak · 破晓日报

每天凌晨自动生成的中英双语晨报：把前一天的 **AI 新闻** 和 **全球要闻** 讲成一听就懂的小故事，同时保留专业深度。
A bilingual morning brief, written automatically every night: yesterday's AI and world news, told as plain-language stories with a professional edge.

**白 · 灰 · 金** 的编辑部风格 · 中文 / English 一键切换 · 浏览器朗读（听简报）· 往期归档 · 每条附原始来源

---

## 它是怎么工作的 · How it works

```
GitHub Actions (cron, 每天 00:15 UTC + 02:40 UTC 兜底)
   │
   ├─ 1. 采集 collect.py ── 25+ RSS/Atom 源（OpenAI、DeepMind、Google AI、NVIDIA、Hugging Face、
   │                         The Verge、TechCrunch、MIT TR、Ars、Wired、Reuters/AP（经 Google News）、
   │                         BBC、Guardian、NYT、Al Jazeera、NPR、DW、CNBC…）
   │                       + Hacker News 高分帖（Algolia API）
   │                       + X / Twitter（可选，配置 X_BEARER_TOKEN 后启用）
   │                       → 只保留前一天（BRIEF_TZ 时区）的条目，去重，统计“多家媒体同时报道”信号
   │
   ├─ 2. 主编 Claude ───── 从几百条候选里挑出 AI 6 条 + 世界 6 条 + 速览 10 条，合并同一事件，写头条与导语
   ├─ 3. 读原文 ────────── 抓取入选报道的正文摘录，给写作提供事实依据
   ├─ 4. 写手 Claude ───── 两个版面并行，逐条写中英双语：故事 · 为什么重要 · 专业视角 · 关键数字 · 名词解释
   │                       （JSON Schema 结构化输出；来源链接由代码从原始条目回填，模型不能编造链接）
   │
   └─ 5. 提交 data/editions/YYYY-MM-DD.json → 部署 GitHub Pages
```

- 静态站点，零服务器：`index.html` + `assets/` 读取 `data/index.json` 和每天的 `data/editions/*.json`。
- 幂等：某天的简报已存在就跳过，所以第二个 cron 只在第一次失败时补跑。
- 失败会让 Action 变红，GitHub 会发邮件提醒你。
- 防注入：抓来的网页文本一律当作“数据”，提示词明确禁止模型执行其中的指令或写入来源没有的事实。

## 一次性设置 · Setup (≈2 分钟)

1. **添加 Claude API 密钥**（必需）：仓库 → Settings → Secrets and variables → Actions → New repository secret
   名称 `ANTHROPIC_API_KEY`，值为你在 [console.anthropic.com](https://console.anthropic.com) 创建的 key。
   或用命令行：`gh secret set ANTHROPIC_API_KEY`
2. （可选）**X / Twitter**：添加 `X_BEARER_TOKEN`（X API v2，需要 Basic 及以上付费档）即可把 OpenAI、Anthropic、Karpathy 等账号的推文纳入候选。账号列表在 `pipeline/sources.json`。
3. 手动跑一次验证：Actions → *Daily brief* → Run workflow。

## 可调参数 · Repository variables

| 变量 | 默认 | 说明 |
|---|---|---|
| `BRIEF_TZ` | `Europe/London` | “前一天”按哪个时区算，例如 `Asia/Shanghai` |
| `BRIEF_MODEL` | `claude-opus-5-5` | 写作模型；想省钱可设 `claude-sonnet-5-5` |
| `BRIEF_EFFORT` | `high` | 思考强度 `low`/`medium`/`high`/`xhigh` |

篇数可在 `pipeline/run.py` 顶部用环境变量 `BRIEF_AI_STORIES` / `BRIEF_WORLD_STORIES` / `BRIEF_QUICK_HITS` 调整；信源在 `pipeline/sources.json` 增删即可。
想换成北京时间凌晨生成：把 `BRIEF_TZ` 设为 `Asia/Shanghai`，并把 workflow 里的 cron 改为 `15 16 * * *`（UTC 16:15 = 北京 00:15）。

**成本**：默认 Opus 5.5，每天约 3 次调用，大约 $1/天上下（随新闻量浮动）；Sonnet 5.5 约一半。

## 本地运行 · Local

```bash
pip install -r pipeline/requirements.txt
python -m pipeline.run --collect-only          # 只采集，输出 candidates.json（不需要 API key）
ANTHROPIC_API_KEY=... python -m pipeline.run   # 生成昨天的简报
python -m http.server 8000                     # 打开 http://localhost:8000
```

## 结构 · Layout

```
index.html, assets/        前端（无构建步骤）
data/index.json            往期目录
data/editions/*.json       每日简报
pipeline/collect.py        采集 + 去重 + 正文摘录（纯标准库）
pipeline/writer.py         Claude 主编 / 写手（结构化输出）
pipeline/run.py            每日入口
pipeline/sources.json      信源清单
.github/workflows/daily.yml  定时任务 + Pages 部署
```

首期（2026-11-03）由同一套采集结果生成，用来展示版式；之后每天由 Action 自动更新。
