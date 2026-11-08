/** 运行时配置（来自 config.js）。 */
const raw = window.__PDK_CONFIG__ ?? ({} as PdkRuntimeConfig)

export const config = {
  title: raw.title || 'PDK 知识服务',
  apiBaseUrl: (raw.apiBaseUrl || '').replace(/\/+$/, ''),
}

/** 跳转 PDS 统一登录（经 pdk-api），登录后回到当前页。 */
export function login(returnTo = location.pathname + location.search) {
  location.href = `${config.apiBaseUrl}/auth/login?return_to=${encodeURIComponent(returnTo)}`
}

export function logout() {
  location.href = `${config.apiBaseUrl}/auth/logout`
}
