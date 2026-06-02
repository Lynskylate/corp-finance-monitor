export type FilingItem = {
  source: string
  source_id: string
  stock_code: string
  stock_name: string
  title: string
  kind: string
  published_at: string
  url: string
  unique_key: string
  file_size: number
}

export type FilingListResponse = {
  items: FilingItem[]
  total: number
  limit: number
  offset: number
}

export type FilingDetailResponse = {
  filing: FilingItem
  stored_path: string | null
}

export type RunItem = {
  id: number
  started_at: string
  finished_at: string
  discovered: number
  fetched: number
  failed: number
}

export type RunListResponse = {
  items: RunItem[]
}

export type SubscriptionItem = {
  id: number
  name: string
  source: string
  stock_code: string
  kind: string
  target: string
  active: boolean
  created_at: string
  updated_at: string
}

export type SubscriptionListResponse = {
  items: SubscriptionItem[]
}

export type StatsResponse = {
  total: number
  by_source: Record<string, number>
  by_kind: Record<string, number>
}
