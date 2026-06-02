import { useQuery } from '@tanstack/react-query'
import { DatabaseZap, FileStack, Radar, SearchCode } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Card, CardContent } from '@/components/ui/card'
import { listFilings, getStats } from '@/features/filings/api'
import { LatestUpdatesPanel, PAGE_SIZE, type LatestFilterState } from '@/features/filings/components/latest-updates-panel'
import { CodeSearchPanel } from '@/features/lookup/components/code-search-panel'
import { SyncStatusPanel } from '@/features/filings/components/sync-status-panel'
import { SubscriptionPanel } from '@/features/filings/components/subscription-panel'

const INITIAL_FILTERS: LatestFilterState = {
  source: '',
  kind: '',
  page: 0,
  since: '',
}

function daysAgoToISO(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

export function HomePage() {
  const [stockCodeInput, setStockCodeInput] = useState('')
  const [activeStockCode, setActiveStockCode] = useState('')
  const [stockPage, setStockPage] = useState(0)
  const [filters, setFilters] = useState<LatestFilterState>(INITIAL_FILTERS)

  function handleFiltersChange(patch: Partial<LatestFilterState>) {
    setFilters((prev) => ({ ...prev, ...patch }))
  }

  function handleStockSubmit() {
    setActiveStockCode(stockCodeInput.trim())
    setStockPage(0)
  }

  // Resolve since value to ISO date
  const sinceDate = filters.since ? daysAgoToISO(Number(filters.since)) : undefined

  const latestQuery = useQuery({
    queryKey: ['latest-filings', filters],
    queryFn: () =>
      listFilings({
        limit: PAGE_SIZE,
        offset: filters.page * PAGE_SIZE,
        source: filters.source || undefined,
        kind: filters.kind || undefined,
        since: sinceDate,
      }),
  })

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

  const statsQuery = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
  })

  const stats = useMemo(() => {
    const data = statsQuery.data
    const sourceCount = data?.by_source ? Object.keys(data.by_source).length : 0
    return [
      {
        label: '公告总数',
        value: String(data?.total ?? latestQuery.data?.total ?? 0),
        hint: '已采集公告数',
        icon: Radar,
      },
      {
        label: '数据源',
        value: String(sourceCount || '—'),
        hint: sourceCount ? Object.entries(data!.by_source).map(([k, v]) => `${k}: ${v}`).join(', ') : '加载中',
        icon: DatabaseZap,
      },
      {
        label: '主视角',
        value: '2',
        hint: '更新流 / 代码查询',
        icon: SearchCode,
      },
      {
        label: '报告类型',
        value: String(data?.by_kind ? Object.keys(data.by_kind).length : '—'),
        hint: '覆盖的报告种类',
        icon: FileStack,
      },
    ]
  }, [statsQuery.data, latestQuery.data?.total])

  return (
    <div className="space-y-6 pb-10">
      <section className="grid gap-6 lg:grid-cols-[1.25fr_0.75fr]">
        <Card className="overflow-hidden">
          <CardContent className="px-6 py-8 sm:px-8">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-emerald-900/15 bg-emerald-50 px-4 py-1.5 text-sm font-medium text-emerald-900">
              Frontend Foundation
            </div>
            <h1 className="max-w-3xl font-['Space_Grotesk'] text-4xl font-bold tracking-tight text-slate-950 sm:text-5xl">
              把企业公告流变成一个可扫、可查、可继续扩展的操作台。
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">
              这一版先把"最近发生什么"和"某个代码最近出了什么"两条主路径打通，给后续 agent
              一个稳定的前端目录、数据流和 UI 基座。
            </p>
          </CardContent>
        </Card>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
          {stats.map((item) => {
            const Icon = item.icon
            return (
              <Card key={item.label}>
                <CardContent className="flex items-start gap-4 px-5 py-5">
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-950 text-slate-50">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-sm text-slate-500">{item.label}</p>
                    <p className="mt-1 font-['Space_Grotesk'] text-3xl font-bold text-slate-950">
                      {item.value}
                    </p>
                    <p className="mt-1 text-sm text-slate-600">{item.hint}</p>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </section>

      <LatestUpdatesPanel
        items={latestQuery.data?.items ?? []}
        total={latestQuery.data?.total ?? 0}
        isLoading={latestQuery.isLoading}
        filters={filters}
        onFiltersChange={handleFiltersChange}
      />

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

      <SyncStatusPanel />

      <SubscriptionPanel />
    </div>
  )
}
