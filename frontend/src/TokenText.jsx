import React from 'react'

/**
 * Render a normalized text with token spans and zero-width chips.
 *
 * tokens: [{id, text, start, end, cue_idx?}]
 * chips:  [{at, label, issue_id, kind}]  (zero-width insertions)
 * tokenIssue: tokenId -> issue
 * highlightIds: Set of token ids to force-flash
 * onTokenClick / onChipClick callbacks receive the issue.
 */
export default function TokenText({
  text, tokens, chips = [], tokenIssue = new Map(),
  activeTokenIds = new Set(), flashTokenIds = new Set(),
  onTokenClick, onChipClick, chipKind = 'missing', className = '',
}) {
  const chipsByAt = new Map()
  for (const chip of chips) {
    if (!chipsByAt.has(chip.at)) chipsByAt.set(chip.at, [])
    chipsByAt.get(chip.at).push(chip)
  }

  const segments = []
  let cursor = 0
  const pushText = (to, key) => {
    if (to > cursor) segments.push({ type: 'text', t: text.slice(cursor, to), key })
  }

  // merge chip offsets with token offsets in stream order
  const events = []
  for (const t of tokens) events.push({ pos: t.start, kind: 'tok', tok: t })
  for (const [at] of chipsByAt) events.push({ pos: at, kind: 'chip-at' })
  events.sort((a, b) => {
    if (a.pos !== b.pos) return a.pos - b.pos
    if (a.kind === b.kind) return 0
    return a.kind === 'chip-at' ? -1 : 1
  })

  let key = 0
  for (const ev of events) {
    if (ev.kind === 'chip-at') {
      pushText(ev.pos, `t${key++}`)
      cursor = Math.max(cursor, ev.pos)
      for (const chip of chipsByAt.get(ev.pos)) {
        segments.push({
          type: 'chip', key: `c${key++}`, chip,
        })
      }
    } else {
      const tok = ev.tok
      pushText(tok.start, `t${key++}`)
      cursor = Math.max(cursor, tok.start)
      segments.push({ type: 'tok', key: `w${key++}`, tok })
      cursor = Math.max(cursor, tok.end)
    }
  }
  pushText(text.length, `t${key++}`)

  return (
    <span className={`token-text ${className}`}>
      {segments.map((seg) => {
        if (seg.type === 'text') return <React.Fragment key={seg.key}>{seg.t}</React.Fragment>
        if (seg.type === 'chip') {
          const { chip } = seg
          return (
            <button
              key={seg.key}
              type="button"
              data-chip-issue={chip.issue_id}
              className={`inline-chip inline-chip-${chipKind}${
                activeTokenIds.has(`chip:${chip.issue_id}`) ? ' active' : ''
              }`}
              title="点击定位问题"
              onClick={() => onChipClick?.(chip.issue_id)}
            >
              +{chip.label}
            </button>
          )
        }
        const { tok } = seg
        const issue = tokenIssue.get(tok.id)
        const classes = ['tok']
        if (issue) classes.push(`tok-${issue.kind}`)
        if (activeTokenIds.has(tok.id)) classes.push('active')
        if (flashTokenIds.has(tok.id)) classes.push('flash')
        return (
          <button
            key={seg.key}
            type="button"
            className={classes.join(' ')}
            data-tok={tok.id}
            data-tok-el={tok.id}
            onClick={issue ? () => onTokenClick?.(issue) : undefined}
          >
            {seg.tok.text}
          </button>
        )
      })}
    </span>
  )
}
