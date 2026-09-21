# 字幕核校台 · Subtitle Proofreader

Python (FastAPI) + React (Vite) 的字幕核校 Web 应用。上传 **SRT 字幕** 与
**校对稿**，服务端归一化标点/空白后，以**词序动态规划跨字幕块对齐**，
自动识别 **缺词、多词、错词片段、错序** 四类问题；前端联动展示字幕时间轴
与校对稿上下文，支持按类型筛选并导出带时间码的核校清单（CSV / Markdown）。

## 一键启动

```bash
docker compose up --build
```

依赖（Python pip / Node npm）会在容器**启动时自动安装**，无需提前配置环境。

启动后访问：

| 服务 | 地址 |
| --- | --- |
| 前端页面（从这里使用） | http://localhost:5173 |
| 后端 API / 健康检查 | http://localhost:8000/api/health |
| 接口文档（Swagger） | http://localhost:8000/docs |

> 首次启动需安装依赖，约 1–2 分钟。停止：`Ctrl+C`；后台运行：
> `docker compose up --build -d`；清除：`docker compose down`。

## 使用方式

1. 打开 http://localhost:5173，点击「选择 SRT」「选择校对稿」（纯文本 txt/md）。
2. 点击「开始核校」，或点「载入示例」快速体验（示例覆盖全部四类问题）。
3. 三栏联动：
   - **字幕时间轴**：每个字幕块显示时间码与高亮问题词；缺失词以 `+词` 内联标记。
   - **校对稿上下文**：按校对稿位置高亮差异词；多出来的词以 `+词` 标记。
   - **问题清单**：点击任意一条，左右两栏自动滚动定位并闪烁对应词。
4. 顶部筛选器按 缺词/多词/错词/错序 过滤；可勾选「仅看有问题的字幕块」。
5. 「导出 CSV」（带 UTF-8 BOM，Excel 直接打开不乱码）或「导出 Markdown」，
   清单含 SMPTE 时间码、字幕块号、字幕原文、校对稿内容及上下文。

## 为什么换行差异不会级联误报

朴素的「逐字幕块 diff」会把整条字幕流在每个块边界切开：一个缺词会让后续
所有块整体错位，产生大量假阳性。本项目的做法：

1. **归一化**（`backend/app/normalize.py`）：NFKC 全/半角统一、弯引号/破折号
   折叠、标点剔除、词内撇号连字符处理（`don't → dont`）、所有空白（含换行）
   折叠为单空格。
2. **跨块词流**：把所有字幕块拼成一条连续词序列——字幕块边界与普通自动换行
   完全等价。CJK 每字一个 token，拉丁/数字按词切分。
3. **锚点 + DP**（`backend/app/align.py`）：先用 64 位**滚动哈希 n-gram** 在
   O(n) 内钉住两侧相同的主体段落（高频但处于同一流位置的 n-gram 同样可用，
   命中均做逐字校验防碰撞）；锚点之间的局部区间再运行 **Needleman–Wunsch
   词序 DP**（匹配 +2 / 替换 −1 / 间隙 −1，小区间精确 DP，大区间退化为
   LCS/difflib），得到真正的替换配对与缺口。
4. **病态文本兜底**：当锚点覆盖不足（大段重写或周期性重复稿，difflib 在这类
   文本上会退化到 O(n²)）时，改用全流**带状 Needleman–Wunsch**（只搜索
   `|j−i| ≤ 48` 的对角带，差异局部性保证正确性），复杂度 O(n·B)。实测
   500 字幕块约 0.13 秒，5000 块周期重复文本约 4.4 秒。
5. **错序检测**：对两侧均未匹配的同形词做交叉判定——跨越对齐锚点或在单遍有序
   扫描中彼此逆序的词对（A B → B A 式换位）聚为一条「错序」，而不是报成一对
   缺词+多词。

问题分类：

- **缺词**：校对稿有、字幕无（插入芯片显示在相邻词之间）。
- **多词**：字幕有、校对稿无。
- **错词片段**：同位置替换（DP sub 配对，可跨多个词，如 `讲座 → 分享`）。
- **错序**：词相同但顺序倒置。

## 本地开发（不使用 Docker）

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（另开终端）
cd frontend
npm install
npm run dev          # 已配置 /api 代理到 http://localhost:8000
```

## 目录结构

```
.
├── docker-compose.yml         # 一条命令启动 api + web
├── backend/
│   ├── Dockerfile             # python:3.12-slim，entrypoint 启动时装依赖
│   ├── docker-entrypoint.sh
│   ├── requirements.txt
│   ├── samples/               # 内置示例（前端“载入示例”）
│   └── app/
│       ├── main.py            # FastAPI：上传/分析/筛选/导出
│       ├── normalize.py       # 标点空白归一化 + CJK/Latin 分词
│       ├── srt.py             # SRT 解析与时间码
│       ├── align.py           # 锚点切分 + Needleman-Wunsch DP + 错序检测
│       └── exporters.py       # CSV(UTF-8 BOM) / Markdown 导出
└── frontend/
    ├── Dockerfile             # node:20-slim，entrypoint 启动时 npm install
    ├── docker-entrypoint.sh
    ├── package.json
    ├── vite.config.js         # /api 代理
    └── src/
        ├── App.jsx            # 三栏联动界面、筛选、导出
        ├── TokenText.jsx      # 词级高亮 + 零宽插入芯片渲染
        └── styles.css
```

## API 摘要

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/analyze` | multipart 上传 `srt` 与 `manuscript`，返回对齐结果与 `job_id` |
| `GET` | `/api/jobs/{id}/issues?kinds=missing,extra&cue=3` | 按类型/字幕块筛选 |
| `GET` | `/api/jobs/{id}/export?format=csv|md&kinds=...` | 导出带时间码清单 |
| `GET` | `/api/sample` | 内置示例文本 |

SRT 编码自动探测（UTF-8/GB18030/Big5 等）。分析任务在服务端内存中保留 1 小时。
