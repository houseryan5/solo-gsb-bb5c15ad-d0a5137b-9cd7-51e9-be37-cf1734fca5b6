import { useEffect, useRef } from 'react'

/** 字幕时间轴：按块展示，问题 token 高亮，点击高亮或徽标可联动定位。 */
export default function TimelinePane({ data, issuesById, activeId, onActivate }) {
  const ref = useRef(null)

  useEffect(() => {
    if (activeId == null) return
    const el = ref.current?.querySelector(`[data-issue="${activeId}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeId])

  return (
    <div className="pane" ref={ref}>
      <div className="pane-title">字幕时间轴</div>
      {data.cues.map((cue) => {
        const marks = data.cue_marks[cue.i] || []
        const issueIds = data.cue_issues[cue.i] || []
        return (
          <div key={cue.i} className={`cue ${issueIds.length ? 'has-issue' : ''}`}>
            <div className="cue-head">
              <span className="cue-time">{cue.start} → {cue.end}</span>
              <span className="cue-badges">
                {issueIds.map((id) => (
                  <button
                    key={id}
                    data-issue={id}
                    className={`dot dot-${issuesById[id].type} ${activeId === id ? 'active' : ''}`}
                    title={`#${id} ${issuesById[id].type}`}
                    onClick={() => onActivate(id)}
                  />
                ))}
              </span>
            </div>
            <div className="cue-text">{renderText(cue.text, marks, issuesById, activeId, onActivate)}</div>
          </div>
        )
      })}
    </div>
  )
}

function renderText(text, marks, issuesById, activeId, onActivate) {
  if (!marks.length) return text
  const sorted = [...marks].sort((x, y) => x.s - y.s)
  const out = []
  let pos = 0
  sorted.forEach((m, k) => {
    if (m.s > pos) out.push(text.slice(pos, m.s))
    const type = issuesById[m.issue]?.type
    out.push(
      <mark
        key={k}
        data-issue={m.issue}
        className={`tk tk-${type} ${activeId === m.issue ? 'active' : ''}`}
        onClick={() => onActivate(m.issue)}
      >
        {text.slice(m.s, m.e)}
      </mark>,
    )
    pos = m.e
  })
  if (pos < text.length) out.push(text.slice(pos))
  return out
}
