import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ArrowLeft, Download, ExternalLink, FolderSearch } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { getFilingDetail } from '@/features/filings/api'
import { formatDateTime, formatFileSize, formatKind } from '@/lib/format'
import { ApiError } from '@/lib/api-client'

export function FilingDetailPage() {
  const params = useParams<{ source: string; sourceId: string }>()
  const hasParams = Boolean(params.source && params.sourceId)

  const detailQuery = useQuery({
    queryKey: ['filing-detail', params.source, params.sourceId],
    queryFn: () => getFilingDetail(params.source ?? '', params.sourceId ?? ''),
    enabled: hasParams,
  })

  const filing = detailQuery.data?.filing
  const error = detailQuery.error
  const isNotFound = error instanceof ApiError && error.isNotFound
  const localFileUrl = hasParams ? `/api/filings/${params.source}/${params.sourceId}/file` : ''
  const openUrl = filing?.url || localFileUrl

  return (
    <div className="space-y-6 pb-10">
      <Button asChild variant="ghost">
        <Link to="/">
          <ArrowLeft className="h-4 w-4" />
          返回总览
        </Link>
      </Button>

      <Card>
        <CardHeader>
          <div className="inline-flex w-fit items-center gap-2 rounded-md border bg-muted px-3 py-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            <FolderSearch className="h-4 w-4" />
            Filing Detail
          </div>
          <CardTitle>公告详情与落盘信息</CardTitle>
          <CardDescription>
            对接 <code className="rounded bg-muted px-1.5 py-0.5 text-xs">/api/filings/{'{source}'}/{'{source_id}'}</code>，展示公告元数据、本地落盘路径及原文链接。
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!hasParams ? (
            <MissingParamsState />
          ) : detailQuery.isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-1/2" />
              <Skeleton className="h-32 w-full" />
            </div>
          ) : isNotFound ? (
            <NotFoundState source={params.source ?? ''} sourceId={params.sourceId ?? ''} />
          ) : error ? (
            <ErrorState message={error.message} />
          ) : filing ? (
            <div className="space-y-6">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-3">
                  <Badge variant="secondary">{formatKind(filing.kind)}</Badge>
                  <span className="text-sm text-muted-foreground">{filing.source.toUpperCase()}</span>
                  {filing.file_size > 0 && (
                    <span className="text-sm text-muted-foreground">{formatFileSize(filing.file_size)}</span>
                  )}
                </div>
                <h1 className="text-2xl font-bold tracking-tight">
                  {filing.title}
                </h1>
                <p className="text-sm text-muted-foreground">
                  {filing.stock_code} · {filing.stock_name || '未标注'} · {formatDateTime(filing.published_at)}
                </p>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <InfoBlock label="唯一键" value={filing.unique_key} />
                <InfoBlock label="源 ID" value={filing.source_id} />
                <InfoBlock label="原始链接" value={filing.url || '（未记录）'} />
                <InfoBlock label="本地落盘路径" value={detailQuery.data?.stored_path ?? '未返回'} />
              </div>

              <div className="flex flex-wrap gap-3">
                <Button asChild>
                  <a href={openUrl} target="_blank" rel="noreferrer">
                    {filing.url ? (
                      <><ExternalLink className="h-4 w-4" /> 打开原文</>
                    ) : (
                      <><Download className="h-4 w-4" /> 打开本地文件</>
                    )}
                  </a>
                </Button>
                {filing.url && (
                  <Button asChild variant="outline">
                    <a href={localFileUrl} target="_blank" rel="noreferrer">
                      <Download className="h-4 w-4" />
                      本地副本
                    </a>
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <NotFoundState source={params.source ?? ''} sourceId={params.sourceId ?? ''} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function InfoBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/50 p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-2 break-all text-sm">{value}</p>
    </div>
  )
}

function MissingParamsState() {
  return (
    <div className="rounded-md border border-dashed p-8 text-center">
      <FolderSearch className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
      <p className="text-sm font-medium">缺少路径参数</p>
      <p className="mt-1 text-sm text-muted-foreground">请通过列表页的"详情"按钮进入公告详情。</p>
      <Button asChild variant="ghost" className="mt-4">
        <Link to="/">返回首页</Link>
      </Button>
    </div>
  )
}

function NotFoundState({ source, sourceId }: { source: string; sourceId: string }) {
  return (
    <div className="rounded-md border border-destructive/50 bg-destructive/10 p-8 text-center">
      <AlertCircle className="mx-auto mb-3 h-8 w-8 text-destructive" />
      <p className="text-sm font-medium text-destructive">公告不存在</p>
      <p className="mt-1 text-sm text-destructive/80">
        未找到 <code className="rounded bg-destructive/20 px-1.5 py-0.5 text-xs">{source}/{sourceId}</code> 对应的公告记录。
      </p>
      <p className="mt-2 text-xs text-muted-foreground">该公告可能尚未被采集，或 source/source_id 不正确。</p>
      <Button asChild variant="ghost" className="mt-4">
        <Link to="/">返回首页</Link>
      </Button>
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-destructive/50 bg-destructive/10 p-8 text-center">
      <AlertCircle className="mx-auto mb-3 h-8 w-8 text-destructive" />
      <p className="text-sm font-medium text-destructive">加载失败</p>
      <p className="mt-1 text-sm text-destructive/80">{message || '网络请求异常，请稍后重试。'}</p>
      <p className="mt-2 text-xs text-muted-foreground">请检查后端服务是否正常运行，或刷新页面重试。</p>
    </div>
  )
}
