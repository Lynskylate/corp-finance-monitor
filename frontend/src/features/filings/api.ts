import { fetchJson } from '@/lib/api-client'
import type {
  FilingDetailResponse,
  FilingItem,
  FilingListResponse,
  RunListResponse,
  StatsResponse,
  SubscriptionListResponse,
  SubscriptionItem,
} from '@/features/filings/types'

export async function listFilings(params: {
  limit?: number
  offset?: number
  stockCode?: string
  source?: string
  kind?: string
  since?: string
}) {
  const search = new URLSearchParams()
  if (params.limit) search.set('limit', String(params.limit))
  if (params.offset) search.set('offset', String(params.offset))
  if (params.stockCode) search.set('stock_code', params.stockCode)
  if (params.source) search.set('source', params.source)
  if (params.kind) search.set('kind', params.kind)
  if (params.since) search.set('since', params.since)

  const query = search.toString()
  const path = query ? `/filings?${query}` : '/filings'
  const data = await fetchJson<FilingListResponse>(path)
  return {
    ...data,
    items: sortFilingsByNewest(data.items),
  }
}

export function getFilingDetail(source: string, sourceId: string) {
  return fetchJson<FilingDetailResponse>(`/filings/${source}/${sourceId}`)
}

export function getStats() {
  return fetchJson<StatsResponse>('/stats')
}

export function listRuns(limit = 20) {
  return fetchJson<RunListResponse>(`/runs?limit=${limit}`)
}

export function listSubscriptions(params?: {
  activeOnly?: boolean
  source?: string
  stockCode?: string
}) {
  const search = new URLSearchParams()
  if (params?.activeOnly) search.set('active_only', 'true')
  if (params?.source) search.set('source', params.source)
  if (params?.stockCode) search.set('stock_code', params.stockCode)
  const query = search.toString()
  const path = query ? `/subscriptions?${query}` : '/subscriptions'
  return fetchJson<SubscriptionListResponse>(path)
}

export async function createSubscription(data: {
  name: string
  source?: string
  stock_code?: string
  kind?: string
  target?: string
  active?: boolean
}) {
  const response = await fetchJson<{ subscription: SubscriptionItem }>(
    '/subscriptions',
    {
      method: 'POST',
      body: JSON.stringify(data),
    },
  )
  return response.subscription
}

export async function deleteSubscription(id: number) {
  return fetchJson<{ ok: boolean }>(`/subscriptions/${id}`, {
    method: 'DELETE',
  })
}

export async function triggerSync(params?: {
  sources?: string[]
  since?: string
}) {
  return fetchJson<{ stats: { discovered: number; fetched: number; failed: number } }>(
    '/sync',
    {
      method: 'POST',
      body: JSON.stringify(params ?? {}),
    },
  )
}

export async function triggerBackfill() {
  return fetchJson<{ stats: { file_size_updated: number; url_updated: number } }>(
    '/backfill',
    { method: 'POST' },
  )
}

function sortFilingsByNewest(items: FilingItem[]) {
  return [...items].sort((left, right) => {
    return new Date(right.published_at).getTime() - new Date(left.published_at).getTime()
  })
}
