import axios from 'axios'
import { Message } from 'view-ui-plus'
import { config, login } from '@/config'

export interface Page<T> {
  total: number
  items: T[]
}

// 登录态为 HttpOnly Cookie（BFF），请求自动携带
export const http = axios.create({ baseURL: config.apiBaseUrl + '/api/v1', timeout: 30_000, withCredentials: true })

http.interceptors.response.use(
  (res) => {
    const body = res.data
    if (body && typeof body.code === 'number' && body.code !== 0) {
      Message.error(body.message || '操作失败')
      return Promise.reject(new Error(body.message))
    }
    return body?.data
  },
  (err) => {
    const status = err.response?.status
    const message = err.response?.data?.message
    if (status === 401) login()
    else Message.error(message || (status ? `请求失败（${status}）` : '网络异常，请稍后重试'))
    return Promise.reject(err)
  },
)

/** 返回值已解包为 data 字段。 */
export const get = <T>(url: string, params?: object) => http.get(url, { params }) as Promise<T>
export const post = <T>(url: string, data?: object) => http.post(url, data) as Promise<T>
export const put = <T>(url: string, data?: object) => http.put(url, data) as Promise<T>
export const del = <T>(url: string) => http.delete(url) as Promise<T>
