import { b02Revision, b02Run, projects } from '@/fixtures/b02'
import type { StageEvent } from '@/domain/types'
import { ServiceNotConnected, type UnlockApi } from './client'

const BASELINE_JOB = 'job_b02_baseline'
const REDESIGN_JOB = 'job_b02_redesign'
const BASELINE_STAGES: StageEvent['stage'][] = ['inspect', 'baseline', 'obstruction']
/** Recorded offsets are replayed faster than written; the UI states the factor. */
export const REPLAY_SCALE = 0.35

/**
 * Serves the bundled illustrative fixture. Event replay keeps the recorded
 * offsets so the interface can be exercised; every record it returns is
 * labelled provenance.kind = 'illustrative'.
 */
export const fixtureApi: UnlockApi = {
  mode: 'fixture',

  async listProjects() {
    return projects
  },

  async latestRevisionId(projectId) {
    if (projectId === b02Revision.project_id) return b02Revision.id
    throw new ServiceNotConnected(`Opening ${projectId}`)
  },

  async getRevision(revisionId) {
    if (revisionId === b02Revision.id) return b02Revision
    throw new ServiceNotConnected(`Revision ${revisionId}`)
  },

  async importPackage() {
    throw new ServiceNotConnected('Importing a package')
  },

  async startRun() {
    return { run_id: b02Run.id, job_id: BASELINE_JOB }
  },

  async requestRedesign() {
    return { job_id: REDESIGN_JOB }
  },

  streamEvents(jobId, onEvent, signal) {
    const events = b02Run.events.filter((e) => BASELINE_STAGES.includes(e.stage) === (jobId === BASELINE_JOB))
    const t0 = events[0]?.t_ms ?? 0
    return new Promise<void>((resolve) => {
      const timers: number[] = []
      const finish = () => {
        timers.forEach(clearTimeout)
        resolve()
      }
      signal.addEventListener('abort', finish, { once: true })
      events.forEach((e: StageEvent, i) => {
        timers.push(
          window.setTimeout(() => {
            onEvent(e)
            if (i === events.length - 1) finish()
          }, (e.t_ms - t0) * REPLAY_SCALE),
        )
      })
    })
  },

  async getRun() {
    return b02Run
  },

  async decide() {
    throw new ServiceNotConnected('Recording a review decision')
  },

  async requestExport() {
    throw new ServiceNotConnected('Exporting a checked package')
  },
}


