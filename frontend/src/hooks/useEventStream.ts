import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'

export function useEventStream(enabled: boolean) {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!enabled) return

    const eventSource = new EventSource('/api/events', { withCredentials: true })

    eventSource.onopen = () => {
      // On reconnect, invalidate all queries to catch any missed events
      queryClient.invalidateQueries()
    }

    eventSource.addEventListener('account_updated', (e) => {
      const data = JSON.parse(e.data)
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      queryClient.invalidateQueries({ queryKey: ['account', data.id] })
    })

    eventSource.addEventListener('role_updated', (e) => {
      const data = JSON.parse(e.data)
      queryClient.invalidateQueries({ queryKey: ['roles'] })
      queryClient.invalidateQueries({ queryKey: ['account', data.account_id] })
    })

    eventSource.addEventListener('job_updated', () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    })

    eventSource.addEventListener('accounts_synced', () => {
      queryClient.invalidateQueries({ queryKey: ['accounts'] })
      queryClient.invalidateQueries({ queryKey: ['roles'] })
    })

    return () => {
      eventSource.close()
    }
  }, [enabled, queryClient])
}
