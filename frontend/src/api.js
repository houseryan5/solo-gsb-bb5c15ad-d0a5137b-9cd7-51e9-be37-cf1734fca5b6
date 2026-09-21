export async function compareFiles(srtFile, scriptFile) {
  const fd = new FormData()
  fd.append('srt', srtFile)
  fd.append('script', scriptFile)
  const res = await fetch('/api/compare', { method: 'POST', body: fd })
  if (!res.ok) {
    let msg = `比对失败（HTTP ${res.status}）`
    try {
      const j = await res.json()
      if (j.detail) msg = j.detail
    } catch { /* 保留默认信息 */ }
    throw new Error(msg)
  }
  return res.json()
}

export async function loadSample() {
  const res = await fetch('/api/sample')
  if (!res.ok) throw new Error('示例加载失败')
  return res.json()
}
