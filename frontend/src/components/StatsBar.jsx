import { typeLabel } from '../export'

const FILTERS = [
  ['all', '全部'],
  ['missing', '缺词'],
  ['extra', '多词'],
  ['misorder', '错序'],
  ['replace', '错词'],
]

export default function StatsBar({ stats, filter, onFilter }) {
  const counts = {
    all: stats.total,
    missing: stats.missing,
    extra: stats.extra,
    misorder: stats.misorder,
    replace: stats.replace,
  }
  return (
    <div className="stats-bar">
      {FILTERS.map(([key, label]) => (
        <button
          key={key}
          className={`chip chip-${key} ${filter === key ? 'on' : ''}`}
          onClick={() => onFilter(key)}
          title={key === 'all' ? '显示全部问题' : `只看「${typeLabel(key)}」`}
        >
          {label}
          <b>{counts[key]}</b>
        </button>
      ))}
      <span className="stats-meta">
        字幕块 {stats.cue_count} · 字幕词 {stats.subtitle_tokens} · 校对稿词 {stats.script_tokens}
      </span>
    </div>
  )
}
