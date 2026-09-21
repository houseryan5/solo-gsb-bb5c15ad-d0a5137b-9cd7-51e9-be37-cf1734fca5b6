import { useMemo, useState } from 'react'
import UploadForm from './components/UploadForm'
import StatsBar from './components/StatsBar'
import TimelinePane from './components/TimelinePane'
import ScriptPane from './components/ScriptPane'
import IssueList from './components/IssueList'
import { exportCSV, exportMarkdown } from './export'

export default function App() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [filter, setFilter] = useState('all')
  const [activeId, setActiveId] = useState(null)

  const issuesById = useMemo(() => {
    const map = {}
    for (const it of data?.issues || []) map[it.id] = it
    return map
  }, [data])

  const filtered = useMemo(
    () => (data?.issues || []).filter((it) => filter === 'all' || it.type === filter),
    [data, filter],
  )

  function handleResult(result) {
    setData(result)
    setFilter('all')
    setActiveId(null)
  }

  if (!data) {
    return (
      <>
        {error && <div className="toast">{error}</div>}
        <UploadForm onResult={handleResult} onError={setError} />
      </>
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>字幕核校工具</h1>
        <div className="topbar-actions">
          <button onClick={() => exportCSV(filtered)} disabled={!filtered.length}>
            导出 CSV 清单
          </button>
          <button onClick={() => exportMarkdown(filtered)} disabled={!filtered.length}>
            导出 Markdown
          </button>
          <button onClick={() => setData(null)}>重新上传</button>
        </div>
      </header>

      <StatsBar stats={data.stats} filter={filter} onFilter={setFilter} />

      {data.issues.length === 0 && (
        <div className="banner-ok">✅ 未发现差异：字幕与校对稿在词序层面完全一致。</div>
      )}

      <main className="layout">
        <IssueList issues={filtered} activeId={activeId} onActivate={setActiveId} />
        <TimelinePane data={data} issuesById={issuesById} activeId={activeId} onActivate={setActiveId} />
        <ScriptPane data={data} issuesById={issuesById} activeId={activeId} onActivate={setActiveId} />
      </main>
    </div>
  )
}
