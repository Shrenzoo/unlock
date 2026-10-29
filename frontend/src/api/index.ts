import type { UnlockApi } from './client'
import { fixtureApi } from './fixtureApi'
import { createHttpApi } from './httpApi'

const base = import.meta.env.VITE_UNLOCK_MODE === 'fixture' ? undefined : (import.meta.env.VITE_UNLOCK_API as string | undefined) ?? 'http://127.0.0.1:8000'

/** Connect locally by default. Illustrative mode requires VITE_UNLOCK_MODE=fixture. */
export const api: UnlockApi = base ? createHttpApi(base) : fixtureApi

export * from './client'
