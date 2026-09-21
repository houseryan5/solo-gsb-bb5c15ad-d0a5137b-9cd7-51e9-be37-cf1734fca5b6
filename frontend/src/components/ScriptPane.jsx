import { useEffect, useRef } from 'react'

/** 校对稿上下文：问题区间高亮（多词为插入点标记），点击联动定位。 */
export default function ScriptPane({ data, issuesById, activeId, onActivate }) {
  const ref = useRef(null)

  useEffect(() => {
    if (activeId == null) return
    const el = ref.current?.querySelector(`[data-issue="${activeId}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [activeId])

  const text = data.script
  const marks = [...data.script_marks].sort((x, y) => x.s - y.s || x.e - y.e)
  const out = []
  let pos = 0
  marks.forEach((m, k) => {
    if (m.s < pos) return // 防御重叠
    if (m.s > pos) out.push(text.slice(pos, m.s))
    const type = issuesById[m.issue]?.type
    const cls = `tk tk-${type} ${activeId === m.issue ? 'active' : ''}`
    if (m.e > m.s) {
      out.push(
        <mark key={k} data-issue={m.issue} className={cls} onClick={() => onActivate(m.issue)}>
          {text.slice(m.s, m.e)}
        </mark>,
      )
    } else {
      // 纯多词：校对稿中无对应文字，在插入点渲染一个可见标记
      out.push(
        <span
          key={k}
          data-issue={m.issue}
          className={`${cls} tk-point`}
          title={`#${m.issue} 此处字幕多词`}
          onClick={() => onActivate(m.issue)}
        />,
      )
    }
    pos = m.e
  })
  if (pos < text.length) out.push(text.slice(pos))

  return (
    <div className="pane" ref={ref}>
      <div className="pane-title">校对稿上下文</div>
      <div className="script-text">{out}</div>
    </div>
  )
}
