import { Link, NavLink, Outlet } from 'react-router-dom'
import { BellRing, SearchCode, TimerReset } from 'lucide-react'

import { cn } from '@/lib/utils'

const navItems = [
  { href: '/#latest', label: '最新更新', icon: TimerReset },
  { href: '/#lookup', label: '代码查询', icon: SearchCode },
]

export function AppShell() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        <header className="sticky top-4 z-20 mb-6 rounded-[28px] border border-emerald-950/10 bg-white/75 px-5 py-4 shadow-[0_20px_60px_-30px_rgba(15,23,42,0.45)] backdrop-blur">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <Link to="/" className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-900 text-emerald-50 shadow-lg shadow-emerald-950/20">
                <BellRing className="h-6 w-6" />
              </div>
              <div>
                <p className="font-['Space_Grotesk'] text-lg font-bold tracking-tight text-slate-950">
                  corp-finance-monitor
                </p>
                <p className="text-sm text-slate-600">
                  企业信息更新流与代码定向检索前端
                </p>
              </div>
            </Link>

            <nav className="flex flex-wrap items-center gap-2">
              {navItems.map((item) => {
                const Icon = item.icon
                return (
                  <NavLink
                    key={item.href}
                    to={item.href}
                    className={({ isActive }) =>
                      cn(
                        'inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition',
                        isActive
                          ? 'border-emerald-900 bg-emerald-900 text-white'
                          : 'border-slate-200 bg-white/90 text-slate-700 hover:border-emerald-400 hover:text-emerald-950',
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
