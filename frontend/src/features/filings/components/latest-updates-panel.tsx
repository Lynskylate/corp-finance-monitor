import { Activity, ArrowDownWideNarrow, ChevronLeft, ChevronRight, Filter } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { FilingTable } from '@/features/filings/components/filing-table'
import { KIND_OPTIONS, SOURCE_OPTIONS } from '@/features/filings/constants'
import type { FilingItem } from '@/features/filings/types'

export const PAGE_SIZE = 20

export type LatestFilterState = {
  source: string
  kind: string
  page: number
}

type LatestUpdatesPanelProps = {
  items: FilingItem[]
  total: number
  isLoading: boolean
  filters: LatestFilterState
  onFiltersChange: (patch: Partial<LatestFilterState>) => void
}

export function LatestUpdatesPanel({
  items,
  total,
  isLoading,
  filters,
  onFiltersChange,
}: LatestUpdatesPanelProps) {
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = filters.page
  const hasActiveFilter = filters.source !== '' || filters.kind !== ''

  function handleSourceToggle(value: string) {
    onFiltersChange({
      source: filters.source === value ? '' : value,
      page: 0,
    })
  }

  function handleKindToggle(value: string) {
    onFiltersChange({
      kind: filters.kind === value ? '' : value,
      page: 0,
    })
  }

  function handleClearFilters() {
    onFiltersChange({ source: '', kind: '', page: 0 })
  }

  return (
    <Card id="latest" className="overflow-hidden">
      <CardHeader className="gap-4 border-b border-slate-200/80 pb-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <CardTitle>最新更新流</CardTitle>
            <CardDescription>
              按 <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">published_at</code> 倒序展示，支持来源和类型过滤。
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-3">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
              <div className="mb-1 flex items-center gap-2 font-medium text-slate-900">
                <Activity className="h-4 w-4 text-emerald-700" />
                数据窗口
              </div>
              <p>命中 {total} 条，第 {currentPage + 1}/{totalPages} 页</p>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <div className="mb-1 flex items-center gap-2 font-medium">
                <ArrowDownWideNarrow className="h-4 w-4" />
                排序策略
              </div>
              <p>前端防御性倒序，确保后端顺序变化不影响阅读。</p>
            </div>
          </div>
        </div>

        {/* ── Filter Bar ── */}
        <div className="flex flex-col gap-3 pt-2">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Filter className="h-4 w-4" />
            <span className="font-medium text-slate-700">过滤</span>
            {hasActiveFilter && (
              <button
                type="button"
                onClick={handleClearFilters}
                className="ml-auto text-xs text-slate-400 underline underline-offset-2 transition hover:text-slate-600"
              >
                清除过滤
              </button>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            <span className="mr-1 text-xs font-medium uppercase tracking-wider text-slate-400 self-center">
              来源
            </span>
            {SOURCE_OPTIONS.map((opt) => (
              <FilterPill
                key={opt.value}
                label={opt.label}
                active={filters.source === opt.value}
                onClick={() => handleSourceToggle(opt.value)}
              />
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            <span className="mr-1 text-xs font-medium uppercase tracking-wider text-slate-400 self-center">
              类型
            </span>
            {KIND_OPTIONS.map((opt) => (
              <FilterPill
                key={opt.value}
                label={opt.label}
                active={filters.kind === opt.value}
                onClick={() => handleKindToggle(opt.value)}
              />
            ))}
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
            <FilingTable items={items} emptyMessage="没有符合过滤条件的更新记录。" />

            {/* ── Pagination Controls ── */}
            {total > PAGE_SIZE && (
              <div className="mt-5 flex items-center justify-between">
                <p className="text-sm text-slate-500">
                  第 {currentPage * PAGE_SIZE + 1}–{Math.min((currentPage + 1) * PAGE_SIZE, total)} 条，共 {total} 条
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={currentPage <= 0}
                    onClick={() => onFiltersChange({ page: currentPage - 1 })}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    上一页
                  </Button>
                  <span className="min-w-[5rem] text-center text-sm font-medium text-slate-700">
                    {currentPage + 1} / {totalPages}
                  </span>
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={currentPage >= totalPages - 1}
                    onClick={() => onFiltersChange({ page: currentPage + 1 })}
                  >
                    下一页
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

/* ── Filter Pill ── */

function FilterPill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
        active
          ? 'border-emerald-600 bg-emerald-50 text-emerald-900 shadow-sm'
          : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50'
      }`}
    >
      {label}
    </button>
  )
}
