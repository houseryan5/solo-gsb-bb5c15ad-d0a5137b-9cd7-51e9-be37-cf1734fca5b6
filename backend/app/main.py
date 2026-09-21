"""FastAPI application: upload, analyze, filter and export."""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response

from .align import KIND_LABEL, analyze
from .exporters import export_csv, export_markdown
from .srt import parse_srt

app = FastAPI(title="字幕核校 Sublime Proofreader")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tiny in-memory job store (single user / demo scale). TTL 1h.
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_TTL = 3600

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "samples"


def _store(job: dict) -> None:
    with _JOBS_LOCK:
        _JOBS[job["id"]] = job
        stale = [k for k, v in _JOBS.items()
                 if time.time() - v["created_at"] > _TTL]
        for k in stale:
            _JOBS.pop(k, None)


def _get(job_id: str) -> dict:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "分析任务不存在或已过期，请重新上传")
    return job


def _decode(upload: UploadFile) -> str:
    raw = upload.file.read()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/analyze")
async def analyze_files(srt: UploadFile = File(...),
                        manuscript: UploadFile = File(...)):
    srt_text = _decode(srt)
    man_text = _decode(manuscript)
    cues = parse_srt(srt_text)
    if not cues:
        raise HTTPException(400, "无法解析 SRT：未找到任何字幕块")
    if not man_text.strip():
        raise HTTPException(400, "校对稿内容为空")
    result = analyze(cues, man_text)
    job = {"id": uuid.uuid4().hex[:12], "created_at": time.time(),
           "srt_name": srt.filename or "subtitles.srt",
           "man_name": manuscript.filename or "manuscript.txt",
           "result": result}
    _store(job)
    return {"job_id": job["id"], "srt_name": job["srt_name"],
            "man_name": job["man_name"], "result": result}


def _filtered(job: dict, kinds: str | None, cue: int | None) -> list[dict]:
    issues = job["result"]["issues"]
    if kinds:
        wanted = {k.strip() for k in kinds.split(",") if k.strip()}
        issues = [d for d in issues if d["kind"] in wanted]
    if cue is not None:
        issues = [d for d in issues
                  if (d.get("cue_start") is not None
                      and d["cue_start"] <= cue <= (d.get("cue_end") or cue))]
    return issues


@app.get("/api/jobs/{job_id}/issues")
def list_issues(job_id: str, kinds: str | None = None,
                cue: int | None = None):
    job = _get(job_id)
    return {"issues": _filtered(job, kinds, cue),
            "stats": job["result"]["stats"]}


@app.get("/api/jobs/{job_id}/export")
def export(job_id: str, format: str = "csv", kinds: str | None = None):
    job = _get(job_id)
    issues = _filtered(job, kinds, None)
    stem = Path(job["srt_name"]).stem or "proofread"
    safe_stem = quote(stem)
    if format == "md":
        body = export_markdown(issues)
        return PlainTextResponse(
            body, media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition":
                     f"attachment; filename=proofread.md; "
                     f"filename*=UTF-8''{safe_stem}-%E6%A0%B8%E6%A0%A1%E6%B8%85%E5%8D%95.md"})
    if format != "csv":
        raise HTTPException(400, "format 仅支持 csv / md")
    body = export_csv(issues)
    return Response(
        content=body.encode("utf-8"), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f"attachment; filename=proofread.csv; "
                 f"filename*=UTF-8''{safe_stem}-proofread.csv"})


@app.get("/api/sample")
def sample():
    srt = (SAMPLE_DIR / "sample.srt").read_text(encoding="utf-8")
    man = (SAMPLE_DIR / "sample_manuscript.txt").read_text(encoding="utf-8")
    return {"srt": srt, "manuscript": man}
