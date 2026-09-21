import { useEffect, useRef } from 'react'
import { typeLabel } from '../export'

/** 问题清单：按类型筛选，点击条目联动字幕时间轴与校对稿。 */
export default function IssueList({ issues, activeId, onActivate }) {
  const ref = useRef(null)

  useEffect(() => {
    if (activeId == null) return
    const el = ref.current?.querySelector(`[data-issue="${activeId}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [activeId])

  if (issues.length === 0) {
    return (
      <div className="pane issue-pane" ref={ref}>
        <div className="pane-title">问题清单</div>
        <div className="empty">✅ 当前筛选条件下没有问题</div>
      </div>
    )
  }

  return (
    <div className="pane issue-pane" ref={ref}>
      <div className="pane-title">问题清单（{issues.length}）</div>
      {issues.map((it) => (
        <button
          key={it.id}
          data-issue={it.id}
          className={`issue-card ${activeId === it.id ? 'active' : ''}`}
          onClick={() => onActivate(it.id)}
        >
          <div className="issue-head">
            <span className={`badge badge-${it.type}`}>{typeLabel(it.type)}</span>
            <span className="issue-time">{it.timecode}</span>
            <span className="issue-id">#{it.id}</span>
          </div>
          <div className="issue-diff">
            <div className="diff-row">
              <span className="diff-tag sub">字幕</span>
              <span className="diff-text">{it.subtitle_tokens.join('') || '（缺）'}</span>
            </div>
            <div className="diff-row">
              <span className="diff-tag ref">校对稿</span>
              <span className="diff-text">{it.script_tokens.join('') || '（无）'}</span>
            </div>
          </div>
          <div className="issue-ctx">字幕：{it.subtitle_excerpt}</div>
          <div className="issue-ctx">稿件：{it.script_excerpt}</div>
        </button>
      ))}
    </div>
  )
}
