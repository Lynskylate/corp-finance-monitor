import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { listFilings } from '@/features/filings/api'
import { CodeSearchPanel } from '@/features/lookup/components/code-search-panel'
import { PAGE_SIZE } from '@/features/filings/components/latest-updates-panel'

export function LookupPage() {
  const [stockCodeInput, setStockCodeInput] = useState('')
  const [activeStockCode, setActiveStockCode] = useState('')
  const [stockPage, setStockPage] = useState(0)

  function handleStockSubmit() {
    setActiveStockCode(stockCodeInput.trim())
    setStockPage(0)
  }

  const stockQuery = useQuery({
    queryKey: ['stock-filings', activeStockCode, stockPage],
    queryFn: () =>
      listFilings({
        stockCode: activeStockCode,
        limit: PAGE_SIZE,
        offset: stockPage * PAGE_SIZE,
      }),
    enabled: activeStockCode.length > 0,
  })

  return (
    <CodeSearchPanel
      value={stockCodeInput}
      onValueChange={setStockCodeInput}
      onSubmit={handleStockSubmit}
      items={stockQuery.data?.items ?? []}
      total={stockQuery.data?.total ?? 0}
      isLoading={stockQuery.isLoading}
      error={stockQuery.error ?? null}
      hasSearched={activeStockCode.length > 0}
      page={stockPage}
      onPageChange={setStockPage}
    />
  )
}
