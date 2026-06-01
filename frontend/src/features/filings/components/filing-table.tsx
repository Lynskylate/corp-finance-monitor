import { ExternalLink, FileSearch } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatDateTime, formatKind, formatRelativeTime } from '@/lib/format'
import type { FilingItem } from '@/features/filings/types'

type FilingTableProps = {
  items: FilingItem[]
  emptyMessage: string
}

export function FilingTable({ items, emptyMessage }: FilingTableProps) {
  if (items.length === 0) {
    return (
      <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50/80 px-6 py-12 text-center text-sm text-slate-500">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-[24px] border border-slate-200">
      <div className="hidden grid-cols-[1.2fr_3fr_1fr_1.2fr_0.9fr] gap-3 bg-slate-950 px-5 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300 md:grid">
        <span>代码</span>
        <span>标题</span>
        <span>类型</span>
        <span>时间</span>
        <span className="text-right">动作</span>
      </div>

      <div className="divide-y divide-slate-200 bg-white">
        {items.map((item) => {
          const relative = formatRelativeTime(item.published_at)
          return (
            <div
              key={item.unique_key}
              className="grid gap-3 px-5 py-4 md:grid-cols-[1.2fr_3fr_1fr_1.2fr_0.9fr] md:items-center"
            >
              <div>
                <p className="font-semibold text-slate-900">{item.stock_code || '未标注'}</p>
                <p className="text-sm text-slate-500">{item.stock_name || item.source.toUpperCase()}</p>
              </div>
              <div>
                <p className="font-medium text-slate-900">{item.title}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">{item.source}</p>
              </div>
              <div>
                <Badge>{formatKind(item.kind)}</Badge>
              </div>
              <div>
                <p className="text-sm text-slate-600">{formatDateTime(item.published_at)}</p>
                {relative && (
                  <p className="mt-0.5 text-xs text-emerald-700">{relative}</p>
                )}
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button asChild size="sm" variant="ghost">
                  <Link to={`/filings/${item.source}/${item.source_id}`}>
                    <FileSearch className="h-4 w-4" />
                    详情
                  </Link>
                </Button>
                <Button asChild size="sm" variant="secondary">
                  <a href={item.url} target="_blank" rel="noreferrer">
                    <ExternalLink className="h-4 w-4" />
                    原文
                  </a>
                </Button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
