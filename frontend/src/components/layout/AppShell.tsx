'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { getUser, clearAuth } from '@/lib/auth'
import type { User } from '@/types'
import {
  LayoutDashboard, Upload, Users,
  ChevronLeft, LogOut, Plug, BarChart3, TrendingUp, FileBarChart2
} from 'lucide-react'

interface AppShellProps {
  children: React.ReactNode
  workspaceId?: number
  workspaceName?: string
}

export default function AppShell({ children, workspaceId, workspaceName }: AppShellProps) {
  const pathname = usePathname()
  const router = useRouter()
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => { setUser(getUser()) }, [])

  function logout() {
    clearAuth()
    router.push('/login')
  }

  const workspaceNavItems = workspaceId ? [
    { href: `/workspaces/${workspaceId}`,            label: 'Dashboard',        icon: LayoutDashboard },
    { href: `/workspaces/${workspaceId}/assets`,     label: 'Assets de IA',     icon: TrendingUp },
    { href: `/workspaces/${workspaceId}/reports`,    label: 'Relatórios',       icon: FileBarChart2 },
    { href: `/workspaces/${workspaceId}/connectors`, label: 'Conectores',       icon: Plug },
    { href: `/workspaces/${workspaceId}/ingest`,     label: 'Ingestão de Dados',icon: Upload },
    { href: `/workspaces/${workspaceId}/users`,      label: 'Membros',          icon: Users },
  ] : []

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + '/')

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-64 bg-brand-900 flex flex-col border-r border-slate-700/50 flex-shrink-0">
        {/* Logo */}
        <div className="p-5 border-b border-slate-700/50">
          <Link href="/workspaces" className="flex items-center gap-3 group">
            <div className="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center">
              <span className="text-white font-bold text-sm">D</span>
            </div>
            <div>
              <p className="text-white font-semibold text-sm leading-tight">Digital Mind</p>
              <p className="text-slate-400 text-xs">AI Discovery</p>
            </div>
          </Link>
        </div>

        {/* Workspace context */}
        {workspaceName && (
          <div className="px-5 py-3 border-b border-slate-700/50">
            <Link href="/workspaces"
              className="flex items-center gap-1.5 text-slate-400 hover:text-white text-xs mb-1 transition-colors">
              <ChevronLeft size={12} /> Todos os clientes
            </Link>
            <p className="text-white font-medium text-sm truncate">{workspaceName}</p>
          </div>
        )}

        {/* Nav */}
        <nav className="flex-1 p-3 space-y-0.5">
          {/* Top-level links (no workspace context) */}
          {!workspaceId && (
            <>
              <Link href="/workspaces"
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                  ${pathname === '/workspaces'
                    ? 'bg-brand-500/20 text-white'
                    : 'text-slate-400 hover:text-white hover:bg-slate-700/50'}`}>
                <LayoutDashboard size={16} />
                Clientes
              </Link>
              {user?.is_platform_admin && (
                <Link href="/admin"
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                    ${isActive('/admin')
                      ? 'bg-brand-500/20 text-white'
                      : 'text-slate-400 hover:text-white hover:bg-slate-700/50'}`}>
                  <BarChart3 size={16} />
                  Admin Dashboard
                </Link>
              )}
            </>
          )}

          {/* Workspace-scoped nav */}
          {workspaceNavItems.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors
                ${pathname === href
                  ? 'bg-brand-500/20 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-700/50'}`}>
              <Icon size={16} />
              {label}
            </Link>
          ))}
        </nav>

        {/* User footer */}
        <div className="p-3 border-t border-slate-700/50">
          {user && (
            <div className="flex items-center gap-3 px-2 py-2">
              <div className="w-7 h-7 rounded-full bg-brand-500 flex items-center justify-center flex-shrink-0">
                <span className="text-white text-xs font-medium">
                  {user.full_name.charAt(0).toUpperCase()}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-white text-xs font-medium truncate">{user.full_name}</p>
                <p className="text-slate-400 text-xs truncate">{user.email}</p>
              </div>
              <button onClick={logout} title="Sair"
                className="text-slate-400 hover:text-white transition-colors">
                <LogOut size={14} />
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 bg-slate-900 overflow-auto">
        {children}
      </main>
    </div>
  )
}
