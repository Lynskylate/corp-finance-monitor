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
