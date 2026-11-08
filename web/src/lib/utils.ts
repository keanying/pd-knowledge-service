import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 相对时间（设计稿"今天 09:12 / 昨天 18:20 / 3 个月前"）。 */
export function formatRelative(value?: string | null) {
  if (!value) return '从未登录'
  const d = new Date(value)
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const diffDays = Math.floor((startOfToday - new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) / 86_400_000)
  if (diffDays <= 0) return `今天 ${hm}`
  if (diffDays === 1) return `昨天 ${hm}`
  if (diffDays < 30) return `${diffDays} 天前`
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} 个月前`
  return `${Math.floor(diffDays / 365)} 年前`
}

/** 解析 CSV（支持引号、逗号、换行转义），首行为表头。 */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  const s = text.replace(/^﻿/, '')
  for (let i = 0; i < s.length; i++) {
    const ch = s[i]
    if (quoted) {
      if (ch === '"' && s[i + 1] === '"') { cell += '"'; i++ }
      else if (ch === '"') quoted = false
      else cell += ch
    } else if (ch === '"') quoted = true
    else if (ch === ',') { row.push(cell); cell = '' }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && s[i + 1] === '\n') i++
      row.push(cell); cell = ''
      if (row.some((c) => c.trim() !== '')) rows.push(row)
      row = []
    } else cell += ch
  }
  row.push(cell)
  if (row.some((c) => c.trim() !== '')) rows.push(row)
  return rows
}

/** 生成 CSV 并下载（带 BOM，Excel 打开中文不乱码）。 */
export function downloadCsv(filename: string, rows: (string | number | null | undefined)[][]) {
  const esc = (v: unknown) => {
    const s = v == null ? '' : String(v)
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const blob = new Blob(['﻿' + rows.map((r) => r.map(esc).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}
