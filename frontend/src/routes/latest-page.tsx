import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { listFilings } from '@/features/filings/api'
import { LatestUpdatesPanel, PAGE_SIZE, type LatestFilterState } from '@/features/filings/components/latest-updates-panel'

const INITIAL_FILTERS: LatestFilterState = {
  exchange: '',
  kind: '',
  page: 0,
  since: '',
}

function daysAgoToISO(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

export function LatestPage() {
  const [filters, setFilters] = useState<LatestFilterState>(INITIAL_FILTERS)

  function handleFiltersChange(patch: Partial<LatestFilterState>) {
    setFilters((prev) => ({ ...prev, ...patch }))
  }

  const sinceDate = filters.since ? daysAgoToISO(Number(filters.since)) : undefined

  const latestQuery = useQuery({
    queryKey: ['latest-filings', filters],
    queryFn: () =>
      listFilings({
        limit: PAGE_SIZE,
        offset: filters.page * PAGE_SIZE,
        exchange: filters.exchange || undefined,
        kind: filters.kind || undefined,
        since: sinceDate,
      }),
  })

  return (
    <LatestUpdatesPanel
      items={latestQuery.data?.items ?? []}
      total={latestQuery.data?.total ?? 0}
      isLoading={latestQuery.isLoading}
      filters={filters}
      onFiltersChange={handleFiltersChange}
    />
  )
}
