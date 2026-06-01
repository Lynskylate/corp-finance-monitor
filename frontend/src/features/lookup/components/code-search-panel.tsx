import { AlertCircle, Search } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { FilingTable } from '@/features/filings/components/filing-table'
import type { FilingItem } from '@/features/filings/types'

type CodeSearchPanelProps = {
  value: string
  onValueChange: (value: string) => void
  onSubmit: () => void
  items: FilingItem[]
  isLoading: boolean
  error: Error | null
}

const CODE_PATTERN = /^[0-9A-Za-z]{1,10}$/

export function CodeSearchPanel({
  value,
  onValueChange,
  onSubmit,
  items,
  isLoading,
  error,
}: CodeSearchPanelProps) {
  const [validationError, setValidationError] = useState<string | null>(null)
  const hasSearched = items.length > 0 || error !== null

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
      <CardHeader className="gap-4 border-b border-slate-200/80 pb-5">
        <CardTitle>按代码查询相关信息</CardTitle>
        <CardDescription>
          面向"我就想看某个代码最近出了什么东西"的路径。先按股票代码查，再按时间倒序看关联公告。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5 pt-6">
        <form className="flex flex-col gap-3 lg:flex-row" onSubmit={handleSubmit} noValidate>
          <div className="flex-1">
            <Input
              value={value}
              onChange={(event) => handleInputChange(event.target.value)}
              placeholder="输入股票代码，例如 000725 或 00700"
            />
            {validationError && (
              <p className="mt-2 flex items-center gap-1.5 text-sm text-red-600">
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
          <div className="rounded-3xl border border-red-200 bg-red-50 px-6 py-8 text-center">
            <AlertCircle className="mx-auto mb-3 h-8 w-8 text-red-400" />
            <p className="text-sm font-medium text-red-800">查询失败</p>
            <p className="mt-1 text-sm text-red-600">
              {error.message || '网络请求异常，请稍后重试。'}
            </p>
            <p className="mt-3 text-xs text-red-400">请检查股票代码是否正确，或确认后端服务是否正常运行。</p>
          </div>
        ) : (
          <FilingTable
            items={items}
            emptyMessage={
              hasSearched
                ? '该代码当前没有查到匹配记录，可能需要确认交易所代码格式。'
                : '输入代码后即可查看该标的的相关更新。'
            }
          />
        )}
      </CardContent>
    </Card>
  )
}
