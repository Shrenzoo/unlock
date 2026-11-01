// Judge credentials stay in this tab and travel only in Authorization headers.
const key = 'unlock.judge.session.v1'
export const judgeOrigin = (import.meta.env.VITE_UNLOCK_JUDGE_API as string | undefined)?.replace(/\/$/, '')
export function judgeToken() { try { return sessionStorage.getItem(key) ?? '' } catch { return '' } }
export function saveJudgeToken(token: string) { sessionStorage.setItem(key, token) }
export function clearJudgeToken() { sessionStorage.removeItem(key) }
export function judgeHeaders(): Record<string, string> { return { Authorization: `Bearer ${judgeToken()}` } }
export function judgeJob() { return new URLSearchParams(location.search).get('judge') }
export async function judgeCall<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!judgeOrigin) throw new Error('Judge service is not configured.')
  const r = await fetch(judgeOrigin + path, { ...init, headers: { ...judgeHeaders(), ...init.headers } })
  const body = await r.json()
  if (r.status === 401 && path !== '/sessions') clearJudgeToken()
  if (!r.ok) throw new Error(body.message ?? 'Judge request failed.')
  return body as T
}
