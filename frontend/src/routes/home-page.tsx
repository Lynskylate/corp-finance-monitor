import { useQuery } from '@tanstack/react-query'
import { DatabaseZap, FileStack, Radar, SearchCode } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Card, CardContent } from '@/components/ui/card'
import { listFilings } from '@/features/filings/api'
import { LatestUpdatesPanel } from '@/features/filings/components/latest-updates-panel'
import { CodeSearchPanel } from '@/features/lookup/components/code-search-panel'

export function HomePage() {
  const [stockCodeInput, setStockCodeInput] = useState('')
  const [activeStockCode, setActiveStockCode] = useState('')

  const latestQuery = useQuery({
    queryKey: ['latest-filings'],
    queryFn: () => listFilings({ limit: 20 }),
  })

  const stockQuery = useQuery({
    queryKey: ['stock-filings', activeStockCode],
    queryFn: () => listFilings({ stockCode: activeStockCode, limit: 50 }),
    enabled: activeStockCode.length > 0,
  })

  const stats = useMemo(
    () => [
      {
        label: '最新窗口',
        value: String(latestQuery.data?.items.length ?? 0),
        hint: '前端默认拉最近 20 条',
        icon: Radar,
      },
      {
        label: '覆盖接口',
        value: '2',
        hint: '/api/filings + 详情接口',
        icon: DatabaseZap,
      },
      {
        label: '主视角',
        value: '2',
        hint: '更新流 / 代码查询',
        icon: SearchCode,
      },
      {
        label: '后续扩展',
        value: '∞',
        hint: '分页、过滤、订阅都可继续叠',
        icon: FileStack,
      },
    ],
    [latestQuery.data?.items.length],
  )

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
              这一版先把“最近发生什么”和“某个代码最近出了什么”两条主路径打通，给后续 agent
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
      />

      <CodeSearchPanel
        value={stockCodeInput}
        onValueChange={setStockCodeInput}
        onSubmit={() => setActiveStockCode(stockCodeInput.trim())}
        items={stockQuery.data?.items ?? []}
        isLoading={stockQuery.isLoading}
      />
    </div>
  )
}
