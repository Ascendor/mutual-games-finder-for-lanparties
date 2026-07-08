import { currentParticipantId } from './playerIdentity'
import type { UsageEventType } from './types'


export function trackUsage(
  eventType: UsageEventType,
  details: Record<string, unknown> = {}
) {
  const participantId = currentParticipantId.value
  if (!participantId) return
  void fetch('/api/app-log/entries', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      participant_id: participantId,
      event_type: eventType,
      details
    }),
    keepalive: true
  }).catch(() => {
    // App logging must never interrupt the user's actual task.
  })
}
