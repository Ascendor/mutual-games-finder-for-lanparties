import { currentParticipantId } from './playerIdentity'
import type { UsageEventType } from './types'


export function trackUsage(
  eventType: UsageEventType,
  details: Record<string, unknown> = {}
) {
  const participantId = currentParticipantId.value
  if (!participantId) return
  void fetch('/api/analytics/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      participant_id: participantId,
      event_type: eventType,
      details
    }),
    keepalive: true
  }).catch(() => {
    // Analytics must never interrupt the user's actual task.
  })
}
