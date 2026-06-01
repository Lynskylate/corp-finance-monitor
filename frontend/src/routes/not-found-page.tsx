import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center pb-10">
      <Card className="max-w-xl">
        <CardContent className="px-8 py-10 text-center">
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.2em] text-slate-400">404</p>
          <h1 className="font-['Space_Grotesk'] text-3xl font-bold text-slate-950">页面不存在</h1>
          <p className="mt-3 text-slate-600">
            当前前端骨架只开放总览与公告详情两条路径，其他页面会在后续子任务里继续补齐。
          </p>
          <Button asChild className="mt-6">
            <Link to="/">返回首页</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
