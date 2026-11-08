export interface Citation {
  chunk_id: string; text: string; score: number; masked: boolean
  source: { kb_id: string; kb_name?: string; doc_id: string; doc_title: string; version_no?: number; page_no?: number; title_path?: string; url?: string }
}
export interface Message { role: 'user' | 'assistant'; content: string; citations?: Citation[]; feedback?: string | null; at?: number; steps?: any[]; elapsed_ms?: number | null }
export interface Conversation { id: string; title: string; updated_at: number; turns?: number; messages?: Message[] }
export interface AppEntry { code: string; name: string; description?: string; categoryName?: string; homeUrl?: string }
export interface Home {
  user: { id: string; name: string; emp_no?: string }
  can_chat: boolean; can_upload: boolean; models: string[]; agent_mode: string; llm: boolean
  quick_questions: string[]; apps: AppEntry[]
  recent_docs: { doc_id: string; title: string; kb_name?: string; version_no?: number; at: number }[]
  conversations: Conversation[]
}

export function login() {
  location.href = '/auth/login'
}

export async function call<T>(method: string, url: string, body?: object): Promise<T> {
  const r = await fetch(url, { method, credentials: 'include', headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined })
  if (r.status === 401) { login(); throw new Error('未登录') }
  const j = await r.json()
  if (j.code !== 0) throw new Error(j.message || '请求失败')
  return j.data as T
}

/** 流式问答：解析 SSE（meta / plan / step / progress / citations / delta / done / error）。 */
export async function chatStream(body: object, on: (event: string, data: any) => void, signal?: AbortSignal) {
  const r = await fetch('/pda/chat', { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })
  if (r.status === 401) { login(); return }
  if (!r.ok || !r.body) {
    const j = await r.json().catch(() => ({}))
    on('error', { message: j.message || `请求失败（${r.status}）` })
    return
  }
  const reader = r.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i)
      buf = buf.slice(i + 2)
      const ev = /^event: (.+)$/m.exec(block)?.[1] || 'message'
      const data = /^data: (.*)$/m.exec(block)?.[1]
      if (data) on(ev, JSON.parse(data))
    }
  }
}

export function greeting(d = new Date()) {
  const h = d.getHours()
  return h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 13 ? '中午好' : h < 18 ? '下午好' : '晚上好'
}

export function ago(ts: number) {
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`
  return `${Math.floor(s / 86400)} 天前`
}
