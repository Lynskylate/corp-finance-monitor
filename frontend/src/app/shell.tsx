import { Link, NavLink, Outlet } from 'react-router-dom'
import { Bell, RefreshCw, SearchCode, TimerReset } from 'lucide-react'

import { cn } from '@/lib/utils'

const navItems = [
  { href: '/#latest', label: '最新更新', icon: TimerReset },
  { href: '/#lookup', label: '代码查询', icon: SearchCode },
  { href: '/#sync', label: '采集状态', icon: RefreshCw },
  { href: '/#subscriptions', label: '订阅管理', icon: Bell },
]

export function AppShell() {
  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        <header className="sticky top-0 z-20 mb-6 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="flex h-14 items-center justify-between">
            <Link to="/" className="flex items-center gap-2">
              <span className="text-lg font-semibold tracking-tight">
                corp-finance-monitor
              </span>
            </Link>

            <nav className="flex items-center gap-1">
              {navItems.map((item) => {
                const Icon = item.icon
                return (
                  <NavLink
                    key={item.href}
                    to={item.href}
                    className={({ isActive }) =>
                      cn(
                        'inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground',
                        isActive
                          ? 'bg-accent text-accent-foreground'
                          : 'text-muted-foreground',
                      )
                    }
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </NavLink>
                )
              })}
            </nav>
          </div>
        </header>

        <main className="flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
