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
      <CardHeader>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>订阅管理</CardTitle>
            <CardDescription>
              创建公告订阅规则，当有新公告匹配时通过 Webhook、邮件或微信推送通知。
            </CardDescription>
          </div>
          <Button
            onClick={() => setShowForm(!showForm)}
            variant={showForm ? 'outline' : 'default'}
            className="shrink-0"
          >
            {showForm ? '取消' : <><Plus className="h-4 w-4" /> 新建订阅</>}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
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
          <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
            <Bell className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
            暂无订阅规则。点击"新建订阅"创建第一条。
          </div>
        ) : (
          <div className="overflow-hidden rounded-md border">
            <div className="divide-y bg-background">
              {subs.map((sub) => (
                <div
                  key={sub.id}
                  className="flex items-center gap-4 px-4 py-3"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="font-medium">{sub.name}</p>
                      <Badge variant={sub.active ? 'default' : 'secondary'} className="text-xs">
                        {sub.active ? '启用' : '停用'}
                      </Badge>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
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
                    className="text-destructive hover:text-destructive hover:bg-destructive/10 shrink-0"
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
    <form onSubmit={handleSubmit} className="rounded-md border bg-muted/50 p-5 space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <label className="text-sm font-medium leading-none">
            名称 *
          </label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例如：关注京东方年报"
            required
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium leading-none">
            股票代码
          </label>
          <Input
            value={stockCode}
            onChange={(e) => setStockCode(e.target.value)}
            placeholder="例如：000725"
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium leading-none">
            来源
          </label>
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <option value="">全部来源</option>
            {SOURCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium leading-none">
            类型
          </label>
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <option value="">全部类型</option>
            {KIND_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="space-y-2">
        <label className="text-sm font-medium leading-none">
          通知目标
        </label>
        <Input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="Webhook URL、邮箱地址或微信 ID"
        />
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-destructive">
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
