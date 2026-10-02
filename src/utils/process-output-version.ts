import type { ProcessTask } from '../types/data-governance'

export function processOutputVersionLabel(task: ProcessTask) {
  return task.input.outputVersionName?.trim() || task.outputVersion || '—'
}
