import { api } from './api'
import type { SyncRun } from './types'

export interface PlayniteProgressState {
  phase: 'upload' | 'processing' | 'completed' | 'failed'
  percent: number
  indeterminate: boolean
  message: string
}

export function stateFromRun(run: SyncRun): PlayniteProgressState {
  const finished = Boolean(run.finished_at)
  const determinate = run.progress_total > 0
  return {
    phase: finished ? (run.success ? 'completed' : 'failed') : 'processing',
    percent: determinate
      ? Math.min(100, Math.round((run.progress_current / run.progress_total) * 100))
      : 0,
    indeterminate: !determinate && !finished,
    message: run.message
  }
}

export async function waitForPlayniteImport(
  runId: number,
  onProgress: (run: SyncRun) => void
): Promise<SyncRun> {
  while (true) {
    const run = await api.playniteImportStatus(runId)
    onProgress(run)
    if (run.finished_at) return run
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
  }
}

export async function waitForGogGalaxyImport(
  runId: number,
  onProgress: (run: SyncRun) => void
): Promise<SyncRun> {
  while (true) {
    const run = await api.gogGalaxyImportStatus(runId)
    onProgress(run)
    if (run.finished_at) return run
    await new Promise((resolve) => window.setTimeout(resolve, 1000))
  }
}
