# 字幕核校工具（Python + React）

上传 SRT 字幕与校对稿，服务端归一化标点与空白后，以**词序动态规划**跨字幕块对齐，
识别**缺词、多词、错序、错词**四类问题；前端联动展示字幕时间轴与校对稿上下文，
可按类型筛选问题，并导出带时间码的核校清单（CSV / Markdown）。

## 启动（一条命令）

```bash
docker compose up --build
```

启动后访问：**http://localhost:8000**

> 前端在镜像构建阶段编译为静态文件；Python 依赖随容器启动自动安装
> （Compose 已挂载 pip 缓存卷，重复启动很快）。无需任何本地环境。

## 使用

1. 打开页面，选择 SRT 字幕文件与校对稿（纯文本），点击「开始比对」；
   也可点击「使用内置示例」快速体验。
2. 结果页三栏联动：**问题清单 | 字幕时间轴 | 校对稿上下文**——
   点击任意问题，三栏自动滚动定位并高亮。
3. 顶部按 缺词 / 多词 / 错序 / 错词 筛选；「导出 CSV 清单」生成带时间码的核校清单。

## 核校原理

1. **归一化**：全角转半角、忽略大小写、剔除全部标点与空白（含换行）。
   字幕换行、分块方式与校对稿的差异不会进入比对，从源头避免级联误报。
2. **切词**：CJK 逐字成词，拉丁字母/数字按词成词，每个 token 记录原文位置。
3. **对齐**：字幕 token 跨字幕块拉平成一条序列，与校对稿 token 序列做全局对齐——
   先以 difflib 匹配块为锚点，锚点间用 Needleman-Wunsch 动态规划精对齐
   （匹配 +2 / 替换 -1 / 空缺 -2）。
4. **归并分类**：相邻差异间只隔着 ≤3 个相同 token 时归并为一处问题：
   - 仅校对稿有 → **缺词**；仅字幕有 → **多词**；
   - 两侧字词多重集基本一致 → **错序**；否则 → **错词**。
5. 每处问题回溯源字幕块时间码与校对稿上下文，生成清单。

## 本地开发

```bash
# 后端（http://localhost:8000）
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload

# 前端（http://localhost:5173，已代理 /api 到 8000）
cd frontend && npm install && npm run dev

# 核心逻辑自测（无需第三方依赖）
python3 backend/tests/test_core.py
```

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/compare` | multipart 上传 `srt` 与 `script` 文件，返回核校结果 JSON |
| GET | `/api/sample` | 返回内置示例的核校结果 |
| GET | `/api/health` | 健康检查 |

## 目录结构

```
├── Dockerfile              # 多阶段：前端构建 + 后端运行时（依赖随启动安装）
├── docker-compose.yml      # 单服务，映射 8000 端口
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py         # FastAPI 入口与静态托管
│   │   ├── tokenizer.py    # 归一化 + 切词
│   │   ├── srt_parser.py   # SRT 解析 / 编码识别
│   │   ├── aligner.py      # 锚点 + Needleman-Wunsch 词序对齐
│   │   └── analyzer.py     # 差异归并与四类问题判定
│   └── tests/test_core.py  # 核心逻辑自测
├── frontend/               # React + Vite
└── samples/                # 内置示例（含缺词/多词/错序/错词用例）
```
