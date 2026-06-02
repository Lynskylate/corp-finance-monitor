import { Download, ExternalLink, FileSearch } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatDateTime, formatFileSize, formatKind, formatRelativeTime } from '@/lib/format'
import type { FilingItem } from '@/features/filings/types'

type FilingTableProps = {
  items: FilingItem[]
  emptyMessage: string
}

export function FilingTable({ items, emptyMessage }: FilingTableProps) {
  if (items.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-md border">
      <div className="hidden grid-cols-[1.2fr_3fr_1fr_1.2fr_0.9fr] gap-3 bg-muted px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted-foreground md:grid">
        <span>代码</span>
        <span>标题</span>
        <span>类型</span>
        <span>时间</span>
        <span className="text-right">动作</span>
      </div>

      <div className="divide-y bg-background">
        {items.map((item) => {
          const relative = formatRelativeTime(item.published_at)
          const fileSizeStr = formatFileSize(item.file_size)
          return (
            <div
              key={item.unique_key}
              className="grid gap-3 px-4 py-3 md:grid-cols-[1.2fr_3fr_1fr_1.2fr_0.9fr] md:items-center"
            >
              <div>
                <p className="font-medium">{item.stock_code || '未标注'}</p>
                <p className="text-sm text-muted-foreground">{item.stock_name || item.source.toUpperCase()}</p>
              </div>
              <div>
                <p className="font-medium">{item.title}</p>
                <div className="mt-1 flex items-center gap-2">
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">{item.source}</p>
                  {fileSizeStr && (
                    <p className="text-xs text-muted-foreground">· {fileSizeStr}</p>
                  )}
                </div>
              </div>
              <div>
                <Badge variant="secondary">{formatKind(item.kind)}</Badge>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">{formatDateTime(item.published_at)}</p>
                {relative && (
                  <p className="mt-0.5 text-xs text-muted-foreground">{relative}</p>
                )}
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button asChild size="sm" variant="ghost">
                  <Link to={`/filings/${item.source}/${item.source_id}`}>
                    <FileSearch className="h-4 w-4" />
                    详情
                  </Link>
                </Button>
                {item.url ? (
                  <Button asChild size="sm" variant="outline">
                    <a href={item.url} target="_blank" rel="noreferrer">
                      <ExternalLink className="h-4 w-4" />
                      原文
                    </a>
                  </Button>
                ) : (
                  <Button asChild size="sm" variant="outline">
                    <a href={`/api/filings/${item.source}/${item.source_id}/file`} target="_blank" rel="noreferrer">
                      <Download className="h-4 w-4" />
                      本地
                    </a>
                  </Button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
