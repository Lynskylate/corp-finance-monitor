import { useQuery } from '@tanstack/react-query'
import { DatabaseZap, FileStack, Radar, SearchCode, TimerReset } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useMemo } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { listFilings, getStats } from '@/features/filings/api'
import { formatDateTime, formatKind, formatRelativeTime } from '@/lib/format'
import type { FilingItem } from '@/features/filings/types'

export function HomePage() {
  const statsQuery = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
  })

  const latestQuery = useQuery({
    queryKey: ['latest-filings', { source: '', kind: '', page: 0, since: '' }],
    queryFn: () => listFilings({ limit: 5, offset: 0 }),
  })

  const stats = useMemo(() => {
    const data = statsQuery.data
    const sourceCount = data?.by_source ? Object.keys(data.by_source).length : 0
    return [
      { label: '公告总数', value: String(data?.total ?? 0), hint: '已采集公告数', icon: Radar },
      {
        label: '数据源',
        value: String(sourceCount || '—'),
        hint: sourceCount ? Object.entries(data!.by_source).map(([k, v]) => `${k}: ${v}`).join(', ') : '加载中',
        icon: DatabaseZap,
      },
      {
        label: '报告类型',
        value: String(data?.by_kind ? Object.keys(data.by_kind).length : '—'),
        hint: '覆盖的报告种类',
        icon: FileStack,
      },
    ]
  }, [statsQuery.data])

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        {stats.map((item) => {
          const Icon = item.icon
          return (
            <Card key={item.label}>
              <CardContent className="flex items-start gap-4 p-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground">
                  <Icon className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">{item.label}</p>
                  <p className="text-2xl font-bold">{item.value}</p>
                  <p className="text-xs text-muted-foreground">{item.hint}</p>
                </div>
              </CardContent>
            </Card>
          )
        })}
      </section>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>最近更新</CardTitle>
            <CardDescription>最新采集的公告</CardDescription>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link to="/latest">
              <TimerReset className="h-4 w-4" />
              查看全部
            </Link>
          </Button>
        </CardHeader>
        <CardContent>
          {latestQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">加载中...</p>
          ) : (latestQuery.data?.items ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">暂无数据</p>
          ) : (
            <div className="space-y-3">
              {(latestQuery.data?.items ?? []).map((item: FilingItem) => {
                const relative = formatRelativeTime(item.published_at)
                return (
                  <div key={item.unique_key} className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">{formatKind(item.kind)}</Badge>
                        <span className="truncate text-sm font-medium">{item.title}</span>
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {item.stock_code || item.source} · {formatDateTime(item.published_at)}
                        {relative && ` · ${relative}`}
                      </p>
                    </div>
                    <Button asChild variant="ghost" size="sm">
                      <Link to={`/filings/${item.source}/${item.source_id}`}>详情</Link>
                    </Button>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <section className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <SearchCode className="h-8 w-8 text-muted-foreground" />
            <div>
              <p className="font-medium">代码查询</p>
              <p className="text-sm text-muted-foreground">按股票代码搜索公告</p>
            </div>
            <Button asChild variant="outline" size="sm" className="ml-auto">
              <Link to="/lookup">前往</Link>
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-4 p-4">
            <DatabaseZap className="h-8 w-8 text-muted-foreground" />
            <div>
              <p className="font-medium">采集状态</p>
              <p className="text-sm text-muted-foreground">查看同步记录与订阅</p>
            </div>
            <Button asChild variant="outline" size="sm" className="ml-auto">
              <Link to="/sync">前往</Link>
            </Button>
          </CardContent>
        </Card>
      </section>
    </div>
  )
}
