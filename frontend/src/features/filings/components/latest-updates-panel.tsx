import { Activity, ArrowDownWideNarrow, CalendarDays, ChevronLeft, ChevronRight, Filter } from 'lucide-react'

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
  since: string
}

type LatestUpdatesPanelProps = {
  items: FilingItem[]
  total: number
  isLoading: boolean
  filters: LatestFilterState
  onFiltersChange: (patch: Partial<LatestFilterState>) => void
}

const DATE_RANGE_OPTIONS = [
  { value: '', label: '全部时间' },
  { value: '7', label: '最近 7 天' },
  { value: '30', label: '最近 30 天' },
  { value: '90', label: '最近 90 天' },
  { value: '365', label: '最近 1 年' },
]

export function LatestUpdatesPanel({
  items,
  total,
  isLoading,
  filters,
  onFiltersChange,
}: LatestUpdatesPanelProps) {
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const currentPage = filters.page
  const hasActiveFilter = filters.source !== '' || filters.kind !== '' || filters.since !== ''

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

  function handleDateRange(value: string) {
    onFiltersChange({
      since: value === filters.since ? '' : value,
      page: 0,
    })
  }

  function handleClearFilters() {
    onFiltersChange({ source: '', kind: '', page: 0, since: '' })
  }

  return (
    <Card id="latest">
      <CardHeader>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <CardTitle>最新更新流</CardTitle>
            <CardDescription>
              按 <code className="rounded bg-muted px-1.5 py-0.5 text-xs">published_at</code> 倒序展示，支持来源、类型和时间范围过滤。
            </CardDescription>
          </div>
          <div className="flex flex-wrap gap-3">
            <div className="rounded-md border bg-muted/50 px-4 py-3 text-sm">
              <div className="mb-1 flex items-center gap-2 font-medium">
                <Activity className="h-4 w-4 text-muted-foreground" />
                数据窗口
              </div>
              <p className="text-muted-foreground">命中 {total} 条，第 {currentPage + 1}/{totalPages} 页</p>
            </div>
            <div className="rounded-md border bg-muted/50 px-4 py-3 text-sm">
              <div className="mb-1 flex items-center gap-2 font-medium">
                <ArrowDownWideNarrow className="h-4 w-4 text-muted-foreground" />
                排序策略
              </div>
              <p className="text-muted-foreground">前端防御性倒序，确保后端顺序变化不影响阅读。</p>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 pt-2">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Filter className="h-4 w-4" />
            <span className="font-medium text-foreground">过滤</span>
            {hasActiveFilter && (
              <button
                type="button"
                onClick={handleClearFilters}
                className="ml-auto text-xs text-muted-foreground underline underline-offset-2 transition hover:text-foreground"
              >
                清除过滤
              </button>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            <span className="mr-1 text-xs font-medium uppercase tracking-wider text-muted-foreground self-center">
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
            <span className="mr-1 text-xs font-medium uppercase tracking-wider text-muted-foreground self-center">
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

          <div className="flex flex-wrap gap-2">
            <span className="mr-1 text-xs font-medium uppercase tracking-wider text-muted-foreground self-center flex items-center gap-1">
              <CalendarDays className="h-3.5 w-3.5" />
              时间
            </span>
            {DATE_RANGE_OPTIONS.map((opt) => (
              <FilterPill
                key={opt.value}
                label={opt.label}
                active={filters.since === opt.value}
                onClick={() => handleDateRange(opt.value)}
              />
            ))}
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : (
          <>
            <FilingTable items={items} emptyMessage="没有符合过滤条件的更新记录。" />

            {total > PAGE_SIZE && (
              <div className="mt-5 flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  第 {currentPage * PAGE_SIZE + 1}–{Math.min((currentPage + 1) * PAGE_SIZE, total)} 条，共 {total} 条
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={currentPage <= 0}
                    onClick={() => onFiltersChange({ page: currentPage - 1 })}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    上一页
                  </Button>
                  <span className="min-w-[5rem] text-center text-sm font-medium">
                    {currentPage + 1} / {totalPages}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
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

function FilterPill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md border px-3 py-1 text-xs font-medium transition-colors ${
        active
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-input bg-background text-muted-foreground hover:bg-accent hover:text-accent-foreground'
      }`}
    >
      {label}
    </button>
  )
}
