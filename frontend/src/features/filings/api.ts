import { fetchJson } from '@/lib/api-client'
import type { FilingDetailResponse, FilingItem, FilingListResponse } from '@/features/filings/types'

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

function sortFilingsByNewest(items: FilingItem[]) {
  return [...items].sort((left, right) => {
    return new Date(right.published_at).getTime() - new Date(left.published_at).getTime()
  })
}
