import { defineStore } from 'pinia'
import { get } from '@/api/http'

export interface Me {
  user: { id: string; name: string; scenic_id?: string; dept_id?: string; emp_no?: string }
  permissions: string[]
  scenic_scope: string[]
  max_security_level: number
  degraded: boolean
  auth_mode: string
}

export const useSession = defineStore('session', {
  state: () => ({ me: null as Me | null }),
  getters: {
    permissions: (s) => new Set(s.me?.permissions ?? []),
  },
  actions: {
    async load() {
      this.me = await get<Me>('/me')
    },
    /** 满足其一即可（权限点与 PDS 中登记的 PDK 权限清单一致） */
    has(...codes: string[]) {
      return codes.some((c) => this.permissions.has(c))
    },
  },
})
