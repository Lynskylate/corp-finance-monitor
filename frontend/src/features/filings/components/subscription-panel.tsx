import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Bell, CheckCircle2, Loader2, Plus, Trash2 } from 'lucide-react'
import { type FormEvent, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  createSubscription,
  deleteSubscription,
  listSubscriptions,
} from '@/features/filings/api'
import { KIND_OPTIONS, SOURCE_OPTIONS } from '@/features/filings/constants'

export function SubscriptionPanel() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)

  const subsQuery = useQuery({
    queryKey: ['subscriptions'],
    queryFn: () => listSubscriptions(),
  })

  const createMutation = useMutation({
    mutationFn: createSubscription,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] })
      setShowForm(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteSubscription,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subscriptions'] })
    },
  })

  const subs = subsQuery.data?.items ?? []

  return (
    <Card id="subscriptions">
      <CardHeader className="gap-4 border-b border-slate-200/80 pb-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>订阅管理</CardTitle>
            <CardDescription>
              创建公告订阅规则，当有新公告匹配时通过 Webhook、邮件或微信推送通知。
            </CardDescription>
          </div>
          <Button
            onClick={() => setShowForm(!showForm)}
            variant={showForm ? 'secondary' : 'default'}
            className="shrink-0"
          >
            {showForm ? '取消' : <><Plus className="h-4 w-4" /> 新建订阅</>}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-5 pt-6">
        {showForm && (
          <SubscriptionForm
            onSubmit={(data) => createMutation.mutate(data)}
            isPending={createMutation.isPending}
            error={createMutation.error}
          />
        )}

        {subsQuery.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : subs.length === 0 ? (
          <div className="rounded-3xl border border-dashed border-slate-300 bg-slate-50/80 px-6 py-10 text-center text-sm text-slate-500">
            <Bell className="mx-auto mb-3 h-8 w-8 text-slate-300" />
            暂无订阅规则。点击"新建订阅"创建第一条。
          </div>
        ) : (
          <div className="overflow-hidden rounded-[24px] border border-slate-200">
            <div className="divide-y divide-slate-200 bg-white">
              {subs.map((sub) => (
                <div
                  key={sub.id}
                  className="flex items-center gap-4 px-5 py-4"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-medium text-slate-900">{sub.name}</p>
                      <Badge variant="outline" className="text-xs">
                        {sub.active ? '启用' : '停用'}
                      </Badge>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                      {sub.source && <span>来源: {sub.source}</span>}
                      {sub.stock_code && <span>代码: {sub.stock_code}</span>}
                      {sub.kind && <span>类型: {sub.kind}</span>}
                      {sub.target && <span className="truncate max-w-[200px]">目标: {sub.target}</span>}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => deleteMutation.mutate(sub.id)}
                    disabled={deleteMutation.isPending}
                    className="text-red-500 hover:text-red-700 hover:bg-red-50 shrink-0"
                  >
                    {deleteMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ── Subscription Form ── */

type SubscriptionFormData = {
  name: string
  source: string
  stock_code: string
  kind: string
  target: string
}

function SubscriptionForm({
  onSubmit,
  isPending,
  error,
}: {
  onSubmit: (data: SubscriptionFormData) => void
  isPending: boolean
  error: Error | null
}) {
  const [name, setName] = useState('')
  const [source, setSource] = useState('')
  const [stockCode, setStockCode] = useState('')
  const [kind, setKind] = useState('')
  const [target, setTarget] = useState('')

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    onSubmit({
      name: name.trim(),
      source: source.trim(),
      stock_code: stockCode.trim(),
      kind: kind.trim(),
      target: target.trim(),
    })
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-2xl border border-slate-200 bg-slate-50/60 p-5 space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">
            名称 *
          </label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例如：关注京东方年报"
            required
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">
            股票代码
          </label>
          <Input
            value={stockCode}
            onChange={(e) => setStockCode(e.target.value)}
            placeholder="例如：000725"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">
            来源
          </label>
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="">全部来源</option>
            {SOURCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">
            类型
          </label>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="flex h-10 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="">全部类型</option>
            {KIND_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">
          通知目标
        </label>
        <Input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="Webhook URL、邮箱地址或微信 ID"
        />
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-600">
          <AlertCircle className="h-4 w-4 shrink-0" />
          创建失败：{error.message}
        </div>
      )}

      <Button type="submit" disabled={isPending || !name.trim()}>
        {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
        创建订阅
      </Button>
    </form>
  )
}
