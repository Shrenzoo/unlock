import type { UnlockApi } from './client'
import { fixtureApi } from './fixtureApi'
import { createHttpApi } from './httpApi'

const base = import.meta.env.VITE_UNLOCK_API as string | undefined

/** Fixture mode unless a coordinator origin is configured. */
export const api: UnlockApi = base ? createHttpApi(base) : fixtureApi

export * from './client'
