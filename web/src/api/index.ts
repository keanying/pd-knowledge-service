import { del, get, post, put, http, type Page } from './http'

export interface Kb {
  id: string; name: string; description?: string; category?: string; scenic_id: string; embed_model: string
  default_security_level: number; review_required: boolean; status: string; owner_id?: string
  doc_count: number; chunk_count: number; my_actions: string[]; created_at: string; updated_at: string
  chunk_strategy: Record<string, unknown>; default_tags: string[]
}
export interface Version {
  id: string; version_no: number; file_name: string; file_size: number; status: string; error?: string
  stats: Record<string, number | string>; created_by?: string; created_at: string; published_at?: string
}
export interface Doc {
  id: string; kb_id: string; title: string; file_type: string; security_level: number; tags: string[]
  status: string; current_version_id?: string; latest_version_no: number; updated_at: string; latest?: Version
}
export interface Citation {
  chunk_id: string; text: string; score: number; chunk_type: string; masked: boolean
  source: { kb_id: string; kb_name?: string; doc_id: string; doc_title: string; version_no?: number; page_no?: number; title_path?: string }
}
export interface SearchResult { query: string; items: Citation[]; latency_ms: number; debug?: Record<string, any> }

export const api = {
  overview: () => get<Record<string, any>>('/stats/overview'),
  kbs: (params?: object) => get<Kb[]>('/kbs', params),
  kb: (id: string) => get<Kb>(`/kbs/${id}`),
  createKb: (body: object) => post<Kb>('/kbs', body),
  updateKb: (id: string, body: object) => put<Kb>(`/kbs/${id}`, body),
  deleteKb: (id: string) => del<void>(`/kbs/${id}`),
  docs: (params: object) => get<Page<Doc>>('/documents', params),
  doc: (id: string) => get<{ document: Doc; versions: Version[]; tasks: any[] }>(`/documents/${id}`),
  upload: (kbId: string, form: FormData) => http.post(`/kbs/${kbId}/documents`, form) as Promise<{ document_id: string; task_id: string }>,
  offline: (id: string) => post<void>(`/documents/${id}:offline`),
  online: (id: string) => post<void>(`/documents/${id}:online`),
  deleteDoc: (id: string) => del<void>(`/documents/${id}`),
  chunks: (versionId: string) => get<Page<any>>(`/versions/${versionId}/chunks`, { page_size: 200 }),
  search: (body: object) => post<SearchResult>('/search', body),
  reviews: () => get<any[]>('/reviews'),
  approve: (vid: string, comment?: string) => post<void>(`/reviews/${vid}:approve`, { comment }),
  reject: (vid: string, comment?: string) => post<void>(`/reviews/${vid}:reject`, { comment }),
  tickets: (params?: object) => get<any[]>('/tickets', params),
  updateTicket: (id: string, body: object) => put<any>(`/tickets/${id}`, body),
  tasks: (params?: object) => get<Page<any>>('/tasks', params),
  retryTask: (id: string) => post<any>(`/tasks/${id}:retry`),
  apiKeys: () => get<any[]>('/api-keys'),
  createApiKey: (body: object) => post<{ key: any; secret: string }>('/api-keys', body),
  disableApiKey: (id: string) => post<any>(`/api-keys/${id}:disable`),
}

export const SECURITY = ['公开', '内部', '秘密', '机密']
export const DOC_STATUS: Record<string, [string, string]> = {
  processing: ['处理中', 'warn'], published: ['已发布', 'ok'], offline: ['已下线', 'none'], deleted: ['已删除', 'bad'],
}
export const VERSION_STATUS: Record<string, [string, string]> = {
  pending: ['待解析', 'none'], parsing: ['解析中', 'warn'], pending_proofread: ['待校对', 'warn'], chunking: ['切片中', 'warn'],
  embedding: ['向量化中', 'warn'], pending_review: ['待审核', 'warn'], published: ['已发布', 'ok'], rejected: ['已驳回', 'bad'],
  superseded: ['历史版本', 'none'], failed: ['失败', 'bad'],
}
export const TASK_STATUS: Record<string, [string, string]> = {
  queued: ['排队中', 'none'], running: ['执行中', 'warn'], succeeded: ['成功', 'ok'], failed: ['失败', 'bad'], cancelled: ['已取消', 'none'],
}
