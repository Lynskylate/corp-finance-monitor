import { Activity, ArrowDownWideNarrow } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { FilingTable } from '@/features/filings/components/filing-table'
import type { FilingItem } from '@/features/filings/types'

type LatestUpdatesPanelProps = {
  items: FilingItem[]
  total: number
  isLoading: boolean
}

export function LatestUpdatesPanel({ items, total, isLoading }: LatestUpdatesPanelProps) {
  return (
    <Card id="latest" className="overflow-hidden">
      <CardHeader className="gap-4 border-b border-slate-200/80 pb-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <CardTitle>最新更新流</CardTitle>
            <CardDescription>
              直接消费 `/api/filings`，按发布时间倒序展示，先把“最近发生了什么”这个视角拉出来。
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-3">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
              <div className="mb-1 flex items-center gap-2 font-medium text-slate-900">
                <Activity className="h-4 w-4 text-emerald-700" />
                最近窗口
              </div>
              <p>当前拉取最近 20 条更新，后续可加分页和来源过滤。</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <div className="mb-1 flex items-center gap-2 font-medium">
                <ArrowDownWideNarrow className="h-4 w-4" />
                排序策略
              </div>
              <p>前端防御性再次按 `published_at` 倒序，避免后端顺序变化影响阅读。</p>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-6">
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : (
          <>
            <p className="mb-4 text-sm text-slate-500">当前查询命中 {total} 条，已展示最新一段。</p>
            <FilingTable items={items} emptyMessage="当前还没有可展示的更新记录。" />
          </>
        )}
      </CardContent>
    </Card>
  )
}
