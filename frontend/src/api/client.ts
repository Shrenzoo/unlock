import type { ErrorEnvelope, ProjectSummary, Revision, RunRecord, StageEvent } from '@/domain/types'

/**
 * The one boundary between the UI and the engineering backend.
 * Screens depend on this interface only; swap the implementation in `api/index.ts`.
 */
/** Public, secret-free decision-policy configuration reported by the coordinator. */
export interface ServiceHealth {
  provider: string
  model: string
  credentials: 'configured' | 'missing'
}

export interface UnlockApi {
  readonly mode: 'fixture' | 'http'
  /** Coordinator origin, or null for the bundled illustrative fixture. */
  readonly origin: string | null
  /** The configured decision policy, or null when no engineering service exists. */
  health(): Promise<ServiceHealth | null>
  listProjects(): Promise<ProjectSummary[]>
  getRevision(revisionId: string): Promise<Revision>
  /** Returns the revision id for a project's latest revision. */
  latestRevisionId(projectId: string): Promise<string>
  /** Hands a locally validated package to the import service. */
  importPackage(files: File[]): Promise<{ job_id: string }>
  /** Baseline search for a frozen target (PRD §8 Analyze). */
  startRun(revisionId: string, body: { target_id: string; policy_id: string; constraint_hash?: string }): Promise<{ run_id: string; job_id: string }>
  /** Bounded model tool loop + independent verification (PRD §8 Redesign, Verify). Proposed endpoint, agree with backend. */
  requestRedesign(runId: string): Promise<{ job_id: string }>
  /** Ordered stage events. Resolves when the job reaches a terminal state or `signal` aborts. */
  streamEvents(jobId: string, onEvent: (e: StageEvent) => void, signal: AbortSignal): Promise<void>
  getRun(runId: string): Promise<RunRecord>
  cancelJob(jobId: string): Promise<void>
  artifactUrl(id: string): string
  decide(candidateId: string, decision: 'accept' | 'reject', inputHash: string): Promise<{ review_event_id: string }>
  requestExport(candidateId: string): Promise<{ job_id: string }>
}

/** Raised when a capability exists in the contract but no service is attached. */
export class ServiceNotConnected extends Error {
  constructor(public readonly capability: string) {
    super(`${capability} needs the UNLOCK engineering service, which is not connected in this build.`)
    this.name = 'ServiceNotConnected'
  }
}

export class ApiError extends Error {
  constructor(public readonly envelope: ErrorEnvelope, public readonly status: number) {
    super(envelope.message)
    this.name = 'ApiError'
  }
}

/** Package rules from PRD §10.1, checked before anything leaves the browser. */
export const PACKAGE_LIMITS = {
  maxCompressedBytes: 25 * 1024 * 1024,
  accepted: ['.zip', '.step', '.stp', '.json'],
  occurrences: [5, 12] as const,
}

export function validatePackage(files: File[]): Array<{ field: string; message: string }> {
  const errors: Array<{ field: string; message: string }> = []
  if (files.length === 0) return [{ field: 'package', message: 'Choose a ZIP, or a STEP file with its manifest.json.' }]
  const total = files.reduce((n, f) => n + f.size, 0)
  if (total > PACKAGE_LIMITS.maxCompressedBytes) {
    errors.push({ field: 'package', message: `Package is ${(total / 1048576).toFixed(1)} MB. The limit is 25 MB compressed.` })
  }
  for (const f of files) {
    const dot = f.name.lastIndexOf('.')
    const ext = dot >= 0 ? f.name.slice(dot).toLowerCase() : ''
    if (!PACKAGE_LIMITS.accepted.includes(ext)) {
      errors.push({ field: f.name, message: `${ext || 'This file type'} is not accepted. Meshes such as STL, OBJ or GLB cannot be analysed.` })
    }
  }
  const isZip = files.length === 1 && files[0].name.toLowerCase().endsWith('.zip')
  if (!isZip) {
    if (!files.some((f) => /\.(step|stp)$/i.test(f.name))) {
      errors.push({ field: 'assembly.step', message: 'A STEP AP214 or AP242 assembly is required.' })
    }
    if (!files.some((f) => f.name.toLowerCase() === 'manifest.json')) {
      errors.push({ field: 'manifest.json', message: 'The engineering manifest is required. Geometry alone cannot be analysed.' })
    }
  }
  return errors
}
