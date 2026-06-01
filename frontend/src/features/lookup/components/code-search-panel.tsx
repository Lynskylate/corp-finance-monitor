import { Search } from 'lucide-react'
import { type FormEvent } from 'react'

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
}

export function CodeSearchPanel({
  value,
  onValueChange,
  onSubmit,
  items,
  isLoading,
}: CodeSearchPanelProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit()
  }

  return (
    <Card id="lookup">
      <CardHeader className="gap-4 border-b border-slate-200/80 pb-5">
        <CardTitle>按代码查询相关信息</CardTitle>
        <CardDescription>
          面向“我就想看某个代码最近出了什么东西”的路径。先按股票代码查，再按时间倒序看关联公告。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5 pt-6">
        <form className="flex flex-col gap-3 lg:flex-row" onSubmit={handleSubmit}>
          <Input
            value={value}
            onChange={(event) => onValueChange(event.target.value)}
            placeholder="输入股票代码，例如 000725 或 00700"
          />
          <Button type="submit" className="lg:w-40">
            <Search className="h-4 w-4" />
            查询
          </Button>
        </form>

        <div className="rounded-3xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-600">
          当前查询直接走 `/api/filings?stock_code=...`，保持和后端最薄的一层契约，后续如果要加行业、来源、类型过滤，可以继续在这一层扩展。
        </div>

        <Separator />

        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : (
          <FilingTable
            items={items}
            emptyMessage={
              value
                ? '该代码当前没有查到匹配记录，可能需要确认交易所代码格式。'
                : '输入代码后即可查看该标的的相关更新。'
            }
          />
        )}
      </CardContent>
    </Card>
  )
}
