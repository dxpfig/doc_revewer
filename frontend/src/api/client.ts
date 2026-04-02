import axios from 'axios'

const baseURL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:18000/api/v1'

/** 默认超时：普通 API。标准导入等长任务请在请求上单独指定 `LONG_API_TIMEOUT_MS`。 */
export const DEFAULT_API_TIMEOUT_MS = 15_000

/** PDF 抽取 + 按页多段 LLM 同步解析，可能需数分钟到十余分钟。 */
export const LONG_API_TIMEOUT_MS = 900_000

export const api = axios.create({
  baseURL,
  timeout: DEFAULT_API_TIMEOUT_MS,
})

export function setToken(token: string | null) {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`
  } else {
    delete api.defaults.headers.common.Authorization
  }
}

export type UserInfo = {
  user_id: string
  role: 'admin' | 'user'
}

export async function login(username: string, role: 'admin' | 'user') {
  const form = new FormData()
  form.append('username', username)
  form.append('role', role)
  const res = await api.post('/auth/login', form)
  return res.data.data as { token: string; username: string; role: 'admin' | 'user' }
}
