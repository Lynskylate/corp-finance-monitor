import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, DatabaseZap, Loader2, Play, RefreshCw, XCircle } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { listRuns, triggerSync, triggerBackfill } from '@/features/filings/api'
import { formatDateTime } from '@/lib/format'

export function SyncStatusPanel() {
  const queryClient = useQueryClient()

  const runsQuery = useQuery({
    queryKey: ['runs'],
    queryFn: () => listRuns(10),
    refetchInterval: 30_000,
  })

  const syncMutation = useMutation({
    mutationFn: () => triggerSync(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['runs'] })
      queryClient.invalidateQueries({ queryKey: ['latest-filings'] })
      queryClient.invalidateQueries({ queryKey: ['stock-filings'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })

  const backfillMutation = useMutation({
    mutationFn: () => triggerBackfill(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['latest-filings'] })
      queryClient.invalidateQueries({ queryKey: ['stock-filings'] })
      queryClient.invalidateQueries({ queryKey: ['stats'] })
    },
  })

  const runs = runsQuery.data?.items ?? []

  return (
    <Card id="sync">
      <CardHeader className="gap-4 border-b border-slate-200/80 pb-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>采集状态</CardTitle>
            <CardDescription>
              查看最近的采集运行记录，手动触发同步，或回填历史数据的链接和文件大小。
            </CardDescription>
          </div>
          <div className="flex gap-2 shrink-0">
            <Button
              onClick={() => backfillMutation.mutate()}
              disabled={backfillMutation.isPending || syncMutation.isPending}
              variant="secondary"
            >
              {backfillMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <DatabaseZap className="h-4 w-4" />
              )}
              {backfillMutation.isPending ? '回填中...' : '回填数据'}
            </Button>
            <Button
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending || backfillMutation.isPending}
            >
              {syncMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {syncMutation.isPending ? '同步中...' : '手动同步'}
            </Button>
          </div>
        </div>

        {syncMutation.isError && (
          <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
            <XCircle className="h-4 w-4 shrink-0" />
            {syncMutation.error instanceof Error && syncMutation.error.message.includes('409')
              ? '已有同步任务正在运行，请稍后再试。'
              : '同步失败，请检查后端服务。'}
          </div>
        )}

        {syncMutation.isSuccess && (
          <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            同步完成：发现 {syncMutation.data?.stats.discovered ?? 0} 条，
            下载 {syncMutation.data?.stats.fetched ?? 0} 条，
            失败 {syncMutation.data?.stats.failed ?? 0} 条。
          </div>
        )}

        {backfillMutation.isSuccess && (
          <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            回填完成：文件大小更新 {backfillMutation.data?.stats.file_size_updated ?? 0} 条，
            链接更新 {backfillMutation.data?.stats.url_updated ?? 0} 条。
          </div>
        )}

        {backfillMutation.isError && (
          <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
            <XCircle className="h-4 w-4 shrink-0" />
            回填失败：{backfillMutation.error instanceof Error ? backfillMutation.error.message : '未知错误'}
          </div>
        )}
      </CardHeader>

      <CardContent className="pt-6">
        {runsQuery.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : runs.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50/80 px-6 py-10 text-center text-sm text-slate-500">
            暂无采集记录。点击"手动同步"开始第一次采集。
          </div>
        ) : (
          <div className="overflow-hidden rounded-[24px] border border-slate-200">
            <div className="hidden grid-cols-[0.5fr_1.5fr_1.5fr_0.8fr_0.8fr_0.8fr] gap-3 bg-slate-950 px-5 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-300 md:grid">
              <span>#</span>
              <span>开始时间</span>
              <span>结束时间</span>
              <span className="text-right">发现</span>
              <span className="text-right">下载</span>
              <span className="text-right">失败</span>
            </div>
            <div className="divide-y divide-slate-200 bg-white">
              {runs.map((run) => (
                <div
                  key={run.id}
                  className="grid gap-3 px-5 py-3 md:grid-cols-[0.5fr_1.5fr_1.5fr_0.8fr_0.8fr_0.8fr] md:items-center"
                >
                  <p className="text-sm font-medium text-slate-500">{run.id}</p>
                  <p className="text-sm text-slate-700">{formatDateTime(run.started_at)}</p>
                  <p className="text-sm text-slate-500">{run.finished_at ? formatDateTime(run.finished_at) : '—'}</p>
                  <p className="text-right">
                    <Badge variant="outline">{run.discovered}</Badge>
                  </p>
                  <p className="text-right">
                    <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">
                      {run.fetched}
                    </Badge>
                  </p>
                  <p className="text-right">
                    {run.failed > 0 ? (
                      <Badge className="bg-red-50 text-red-700 border-red-200 flex items-center gap-1 w-fit ml-auto">
                        <AlertCircle className="h-3 w-3" />
                        {run.failed}
                      </Badge>
                    ) : (
                      <Badge variant="outline">0</Badge>
                    )}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-4 flex items-center gap-2 text-xs text-slate-400">
          <RefreshCw className="h-3.5 w-3.5" />
          每 30 秒自动刷新
        </div>
      </CardContent>
    </Card>
  )
}
