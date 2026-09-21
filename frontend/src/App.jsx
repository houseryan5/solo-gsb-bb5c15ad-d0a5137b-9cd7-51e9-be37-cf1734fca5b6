import React, { useCallback, useMemo, useRef, useState } from 'react'
import TokenText from './TokenText.jsx'

const KIND_META = {
  missing: { label: '缺词', cls: 'k-missing' },
  extra: { label: '多词', cls: 'k-extra' },
  substitution: { label: '错词', cls: 'k-sub' },
  reorder: { label: '错序', cls: 'k-reorder' },
}

export default function App() {
  const [srtFile, setSrtFile] = useState(null)
  const [manFile, setManFile] = useState(null)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [kinds, setKinds] = useState(() => new Set(Object.keys(KIND_META)))
  const [onlyProblemCues, setOnlyProblemCues] = useState(false)
  const [activeIssueId, setActiveIssueId] = useState(null)
  const [flashTokenIds, setFlashTokenIds] = useState(() => new Set())
  const [jobId, setJobId] = useState(null)

  const cueRefs = useRef(new Map())
  const manRef = useRef(null)
  const listRefs = useRef(new Map())

  const issues = data?.result?.issues || data?.issues || []
  const result = data?.result || data
  const filtered = useMemo(
    () => issues.filter((i) => kinds.has(i.kind)),
    [issues, kinds],
  )
  const filteredIds = useMemo(() => new Set(filtered.map((i) => i.id)), [filtered])

  const refTokenIssue = useMemo(() => {
    const m = new Map()
    for (const iss of filtered) {
      for (const id of iss.ref_token_ids || []) {
        if (!m.has(id)) m.set(id, iss)
      }
    }
    return m
  }, [filtered])
  const hypTokenIssue = useMemo(() => {
    const m = new Map()
    for (const iss of filtered) {
      for (const id of iss.hyp_token_ids || []) {
        if (!m.has(id)) m.set(id, iss)
      }
    }
    return m
  }, [filtered])

  const cueIssueCount = useMemo(() => {
    const m = new Map()
    for (const iss of filtered) {
      for (let c = iss.cue_start; c <= (iss.cue_end ?? iss.cue_start); c++) {
        if (c != null) m.set(c, (m.get(c) || 0) + 1)
      }
    }
    return m
  }, [filtered])

  const activeIssue = issues.find((i) => i.id === activeIssueId) || null
  const activeTokenIds = useMemo(() => {
    if (!activeIssue) return new Set()
    const s = new Set([
      ...(activeIssue.hyp_token_ids || []),
      ...(activeIssue.ref_token_ids || []),
      `chip:${activeIssue.id}`,
    ])
    return s
  }, [activeIssue])

  const upload = useCallback(async (srtText = null, manText = null, names = {}) => {
    setLoading(true)
    setError('')
    try {
      let body
      let headers = {}
      if (srtText != null) {
        const fd = new FormData()
        fd.append('srt', new Blob([srtText], { type: 'text/plain' }),
                  names.srt || 'sample.srt')
        fd.append('manuscript', new Blob([manText], { type: 'text/plain' }),
                  names.man || 'sample.txt')
        body = fd
      } else {
        if (!srtFile || !manFile) {
          setError('请先选择 SRT 字幕文件与校对稿文本文件')
          setLoading(false)
          return
        }
        const fd = new FormData()
        fd.append('srt', srtFile)
        fd.append('manuscript', manFile)
        body = fd
      }
      const resp = await fetch('/api/analyze', { method: 'POST', body, headers })
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}))
        throw new Error(detail.detail || `分析失败 (${resp.status})`)
      }
      const json = await resp.json()
      setJobId(json.job_id)
      setData(json)
      setActiveIssueId(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [srtFile, manFile])

  const loadSample = useCallback(async () => {
    const resp = await fetch('/api/sample')
    const s = await resp.json()
    await upload(s.srt, s.manuscript, { srt: '示例字幕.srt', man: '校对稿.txt' })
  }, [upload])

  const flash = useCallback((ids) => {
    setFlashTokenIds(new Set(ids))
    window.setTimeout(() => setFlashTokenIds(new Set()), 1400)
  }, [])

  const focusIssue = useCallback((iss) => {
    setActiveIssueId(iss.id)
    // cue
    const cueIdx = iss.cue_chip?.cue_index ?? iss.cue_start
    if (cueIdx != null) {
      cueRefs.current.get(cueIdx)?.scrollIntoView(
        { behavior: 'smooth', block: 'center' })
    }
    // manuscript: prefer first reference token, fall back to an
    // insertion chip (extra words)
    const tokId = iss.ref_token_ids?.[0]
    let el = null
    if (tokId != null) {
      el = manRef.current?.querySelector(`[data-tok-el="${tokId}"]`)
    }
    if (!el && iss.ref_chip) {
      el = manRef.current?.querySelector(`[data-chip-issue="${iss.id}"]`)
    }
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    flash([...(iss.hyp_token_ids || []), ...(iss.ref_token_ids || [])])
    listRefs.current.get(iss.id)?.scrollIntoView(
      { behavior: 'smooth', block: 'nearest' })
  }, [flash])

  const focusCue = useCallback((cueIdx) => {
    const span = result?.cue_ref_spans?.[String(cueIdx)]
    if (!span) return
    // find token at span start
    const tok = result?.ref?.tokens?.find((t) => t.start >= span[0])
    const el = manRef.current?.querySelector(
      `[data-tok-el="${tok?.id}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [result])

  const toggleKind = (k) => {
    setKinds((prev) => {
      const next = new Set(prev)
      if (next.has(k)) next.delete(k)
      else next.add(k)
      return next
    })
  }

  const exportUrl = (fmt) => {
    if (!jobId) return '#'
    const ks = [...kinds].join(',')
    return `/api/jobs/${jobId}/export?format=${fmt}&kinds=${encodeURIComponent(ks)}`
  }

  const cues = result?.cues || []
  const ref = result?.ref

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">字</span>
          <div>
            <h1>字幕核校台</h1>
            <p className="subtitle">跨字幕块词序对齐 · 缺词 / 多词 / 错词 / 错序检测</p>
          </div>
        </div>
        <div className="actions">
          <label className="filebtn">
            选择 SRT
            <input type="file" accept=".srt,text/plain" onChange={(e) => setSrtFile(e.target.files[0])} hidden />
          </label>
          <label className="filebtn">
            选择校对稿
            <input type="file" accept=".txt,.md,text/plain" onChange={(e) => setManFile(e.target.files[0])} hidden />
          </label>
          <button className="btn primary"
                  disabled={loading || !srtFile || !manFile}
                  onClick={() => upload()}>
            {loading ? '核校中…' : '开始核校'}
          </button>
          <button className="btn ghost" onClick={loadSample} disabled={loading}>载入示例</button>
        </div>
      </header>

      {(srtFile || manFile) && (
        <div className="files">
          {srtFile && <span className="tag">SRT：{srtFile.name}</span>}
          {manFile && <span className="tag">校对稿：{manFile.name}</span>}
        </div>
      )}
      {error && <div className="error">{error}</div>}

      {result && (
        <>
          <div className="toolbar">
            <div className="filters">
              {Object.entries(KIND_META).map(([k, meta]) => {
                const count = result.stats[k] || 0
                const on = kinds.has(k)
                return (
                  <button key={k}
                          className={`filter ${meta.cls} ${on ? 'on' : 'off'}`}
                          onClick={() => toggleKind(k)}>
                    {meta.label} <b>{count}</b>
                  </button>
                )
              })}
              <label className="switch">
                <input type="checkbox" checked={onlyProblemCues}
                       onChange={(e) => setOnlyProblemCues(e.target.checked)} />
                仅看有问题的字幕块
              </label>
            </div>
            <div className="exports">
              <a className="btn ghost" href={exportUrl('csv')}>导出 CSV</a>
              <a className="btn ghost" href={exportUrl('md')}>导出 Markdown</a>
            </div>
          </div>

          <div className="stats">
            共 {result.counts.cues} 个字幕块 · 字幕 {result.counts.hyp_words} 词 ·
            校对稿 {result.counts.ref_words} 词 ·
            当前筛选 <b>{filtered.length}</b> / {result.stats.total} 处问题
          </div>

          <main className="panes">
            {/* ---- cue timeline ---- */}
            <section className="pane cues-pane">
              <h2>字幕时间轴</h2>
              <div className="pane-body">
                {cues.map((cue) => {
                  const cnt = cueIssueCount.get(cue.index) || 0
                  const chipData = (cue.chips || []).map((c) => ({ ...c }))
                  if (onlyProblemCues && cnt === 0) return null
                  const cueTokens = (result.hyp_tokens || [])
                    .filter((t) => t.cue_idx === cue.index)
                  const isActive = activeIssue &&
                    cue.index >= activeIssue.cue_start &&
                    cue.index <= (activeIssue.cue_end ?? activeIssue.cue_start)
                  return (
                    <article key={cue.index}
                             ref={(el) => el && cueRefs.current.set(cue.index, el)}
                             className={`cue ${cnt ? 'has-issue' : ''} ${
                                 isActive ? 'focused' : ''}`}
                             onClick={() => focusCue(cue.index)}>
                      <div className="cue-head">
                        <span className="cue-no">#{cue.index}</span>
                        <span className="tc">
                          {cue.start_tc} → {cue.end_tc}
                        </span>
                        {cnt > 0 && <span className="badge">{cnt}</span>}
                      </div>
                      <div className="cue-body">
                        <TokenText
                          text={cue.norm_text}
                          tokens={cueTokens}
                          chips={chipData}
                          chipKind="missing"
                          tokenIssue={hypTokenIssue}
                          activeTokenIds={activeTokenIds}
                          flashTokenIds={flashTokenIds}
                          onChipClick={(id) => {
                            const iss = issues.find((x) => x.id === id)
                            if (iss) focusIssue(iss)
                          }}
                          onTokenClick={(iss) => focusIssue(iss)}
                        />
                      </div>
                    </article>
                  )
                })}
              </div>
            </section>

            {/* ---- manuscript ---- */}
            <section className="pane man-pane">
              <h2>校对稿上下文</h2>
              <div className="pane-body" ref={manRef}>
                <div className={`man-text ${activeIssue ? 'has-focus' : ''}`}>
                  <TokenText
                    text={ref.norm_text}
                    tokens={ref.tokens}
                    chips={(ref.chips || []).map((c) => ({ ...c }))}
                    chipKind="extra"
                    tokenIssue={refTokenIssue}
                    activeTokenIds={activeTokenIds}
                    flashTokenIds={flashTokenIds}
                    onChipClick={(id) => {
                      const iss = issues.find((x) => x.id === id)
                      if (iss) focusIssue(iss)
                    }}
                    onTokenClick={(iss) => focusIssue(iss)}
                  />
                </div>
              </div>
            </section>

            {/* ---- issues list ---- */}
            <section className="pane issues-pane">
              <h2>问题清单（{filtered.length}）</h2>
              <div className="pane-body">
                {filtered.length === 0 && (
                  <p className="empty">当前筛选条件下没有问题 🎉</p>
                )}
                {filtered.map((iss) => (
                  <button key={iss.id} type="button"
                          ref={(el) => el && listRefs.current.set(iss.id, el)}
                          className={`issue issue-${iss.kind} ${
                              activeIssueId === iss.id ? 'focused' : ''}`}
                          onClick={() => focusIssue(iss)}>
                    <div className="issue-row1">
                      <span className={`kind ${KIND_META[iss.kind].cls}`}>
                        {iss.kind_label}
                      </span>
                      <span className="issue-id">{iss.id}</span>
                      {iss.start_tc && <span className="tc">{iss.start_tc}</span>}
                      {iss.cue_start != null && (
                        <span className="cue-tag">#{iss.cue_start}</span>
                      )}
                    </div>
                    <div className="issue-title">{iss.title}</div>
                    {iss.ref_context && (
                      <div className="issue-ctx">{iss.ref_context}</div>
                    )}
                  </button>
                ))}
              </div>
            </section>
          </main>
        </>
      )}

      {!result && (
        <div className="welcome">
          <h2>上传 SRT 字幕与校对稿，一键核校</h2>
          <ul>
            <li>服务端归一化标点与空白，跨字幕块做词序动态规划对齐</li>
            <li>识别 <b>缺词、多词、错词片段、错序</b>，换行差异不产生级联误报</li>
            <li>时间轴与校对稿联动高亮，支持按类型筛选并导出带时间码清单</li>
          </ul>
          <button className="btn primary big" onClick={loadSample} disabled={loading}>
            {loading ? '载入中…' : '先看一个示例'}
          </button>
        </div>
      )}
    </div>
  )
}
