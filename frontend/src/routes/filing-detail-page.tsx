import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ExternalLink, FolderSearch } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { getFilingDetail } from '@/features/filings/api'
import { formatDateTime, formatKind } from '@/lib/format'

export function FilingDetailPage() {
  const params = useParams<{ source: string; sourceId: string }>()

  const detailQuery = useQuery({
    queryKey: ['filing-detail', params.source, params.sourceId],
    queryFn: () => getFilingDetail(params.source ?? '', params.sourceId ?? ''),
    enabled: Boolean(params.source && params.sourceId),
  })

  const filing = detailQuery.data?.filing

  return (
    <div className="space-y-6 pb-10">
      <Button asChild variant="ghost">
        <Link to="/">
          <ArrowLeft className="h-4 w-4" />
          返回总览
        </Link>
      </Button>

      <Card>
        <CardHeader className="gap-4 border-b border-slate-200/80 pb-5">
          <div className="inline-flex w-fit items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            <FolderSearch className="h-4 w-4" />
            Filing Detail
          </div>
          <CardTitle>公告详情与落盘信息</CardTitle>
          <CardDescription>
            这里对接 `/api/filings/{'{source}'}/{'{source_id}'}`，后续可继续扩展成附件预览、变更 diff 或订阅入口。
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-6">
          {detailQuery.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-1/2" />
              <Skeleton className="h-32 w-full" />
            </div>
          ) : filing ? (
            <div className="space-y-6">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-3">
                  <Badge>{formatKind(filing.kind)}</Badge>
                  <span className="text-sm text-slate-500">{filing.source.toUpperCase()}</span>
                </div>
                <h1 className="font-['Space_Grotesk'] text-3xl font-bold tracking-tight text-slate-950">
                  {filing.title}
                </h1>
                <p className="text-sm text-slate-600">
                  {filing.stock_code} · {filing.stock_name || '未标注'} · {formatDateTime(filing.published_at)}
                </p>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <InfoBlock label="唯一键" value={filing.unique_key} />
                <InfoBlock label="源 ID" value={filing.source_id} />
                <InfoBlock label="原始链接" value={filing.url} />
                <InfoBlock label="本地落盘路径" value={detailQuery.data?.stored_path ?? '未返回'} />
              </div>

              <Button asChild>
                <a href={filing.url} target="_blank" rel="noreferrer">
                  <ExternalLink className="h-4 w-4" />
                  打开原文
                </a>
              </Button>
            </div>
          ) : (
            <p className="text-sm text-slate-500">未找到对应公告，可能 source/source_id 不存在。</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function InfoBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-slate-50/80 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">{label}</p>
      <p className="mt-2 break-all text-sm text-slate-700">{value}</p>
    </div>
  )
}
