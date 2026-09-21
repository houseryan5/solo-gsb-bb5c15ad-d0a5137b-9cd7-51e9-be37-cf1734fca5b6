const TYPE_LABEL = {
  missing: '缺词',
  extra: '多词',
  misorder: '错序',
  replace: '错词',
}

export function typeLabel(t) {
  return TYPE_LABEL[t] || t
}

function csvCell(v) {
  return '"' + String(v ?? '').replaceAll('"', '""') + '"'
}

function download(blob, name) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function rows(issues) {
  return issues.map((it, i) => [
    i + 1,
    typeLabel(it.type),
    it.timecode,
    it.subtitle_tokens.join('') || '—',
    it.script_tokens.join('') || '—',
    it.subtitle_excerpt,
    it.script_excerpt,
  ])
}

const HEAD = ['序号', '类型', '时间码', '字幕问题片段', '校对稿对应片段', '字幕上下文', '校对稿上下文']

export function exportCSV(issues) {
  // 带 BOM，保证 Excel 打开中文不乱码
  const csv = '\ufeff' + [HEAD, ...rows(issues)]
    .map((r) => r.map(csvCell).join(','))
    .join('\r\n')
  download(new Blob([csv], { type: 'text/csv;charset=utf-8' }), '字幕核校清单.csv')
}

export function exportMarkdown(issues) {
  const esc = (s) => String(s ?? '').replaceAll('|', '\\|').replaceAll('\n', ' ')
  const lines = [
    '# 字幕核校清单',
    '',
    `| ${HEAD.join(' | ')} |`,
    `| ${HEAD.map(() => '---').join(' | ')} |`,
    ...rows(issues).map((r) => `| ${r.map(esc).join(' | ')} |`),
    '',
  ]
  download(new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' }), '字幕核校清单.md')
}
