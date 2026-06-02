import { AlertCircle, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { FilingTable } from '@/features/filings/components/filing-table'
import { PAGE_SIZE } from '@/features/filings/components/latest-updates-panel'
import type { FilingItem } from '@/features/filings/types'

type CodeSearchPanelProps = {
  value: string
  onValueChange: (value: string) => void
  onSubmit: () => void
  items: FilingItem[]
  total: number
  isLoading: boolean
  error: Error | null
  hasSearched: boolean
  page: number
  onPageChange: (page: number) => void
}

const CODE_PATTERN = /^[0-9A-Za-z]{1,10}$/

export function CodeSearchPanel({
  value,
  onValueChange,
  onSubmit,
  items,
  total,
  isLoading,
  error,
  hasSearched,
  page,
  onPageChange,
}: CodeSearchPanelProps) {
  const [validationError, setValidationError] = useState<string | null>(null)
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = value.trim()

    if (!trimmed) {
      setValidationError('请输入股票代码')
      return
    }
    if (!CODE_PATTERN.test(trimmed)) {
      setValidationError('代码格式不正确，仅支持字母和数字（最多 10 位）')
      return
    }

    setValidationError(null)
    onSubmit()
  }

  function handleInputChange(next: string) {
    onValueChange(next)
    if (validationError) setValidationError(null)
  }

  return (
    <Card id="lookup">
      <CardHeader>
        <CardTitle>按代码查询相关信息</CardTitle>
        <CardDescription>
          面向"我就想看某个代码最近出了什么东西"的路径。先按股票代码查，再按时间倒序看关联公告。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <form className="flex flex-col gap-3 lg:flex-row" onSubmit={handleSubmit} noValidate>
          <div className="flex-1">
            <Input
              value={value}
              onChange={(event) => handleInputChange(event.target.value)}
              placeholder="输入股票代码，例如 000725 或 00700"
            />
            {validationError && (
              <p className="mt-2 flex items-center gap-1.5 text-sm text-destructive">
                <AlertCircle className="h-4 w-4 shrink-0" />
                {validationError}
              </p>
            )}
          </div>
          <Button type="submit" className="lg:w-40">
            <Search className="h-4 w-4" />
            查询
          </Button>
        </form>

        <Separator />

        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : error ? (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-6 text-center">
            <AlertCircle className="mx-auto mb-3 h-8 w-8 text-destructive" />
            <p className="text-sm font-medium text-destructive">查询失败</p>
            <p className="mt-1 text-sm text-destructive/80">
              {error.message || '网络请求异常，请稍后重试。'}
            </p>
            <p className="mt-3 text-xs text-muted-foreground">请检查股票代码是否正确，或确认后端服务是否正常运行。</p>
          </div>
        ) : (
          <>
            <FilingTable
              items={items}
              emptyMessage={
                hasSearched
                  ? '该代码当前没有查到匹配记录，可能需要确认交易所代码格式。'
                  : '输入代码后即可查看该标的的相关更新。'
              }
            />
            {hasSearched && total > PAGE_SIZE && (
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  第 {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} 条，共 {total} 条
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={page <= 0}
                    onClick={() => onPageChange(page - 1)}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    上一页
                  </Button>
                  <span className="min-w-[5rem] text-center text-sm font-medium">
                    {page + 1} / {totalPages}
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={page >= totalPages - 1}
                    onClick={() => onPageChange(page + 1)}
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
