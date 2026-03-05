'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import { listWorkspaces, listConnectors, listAssets } from '@/lib/api'
import { getUser } from '@/lib/auth'
import type { Workspace, Connector, DiscoveredAsset } from '@/types'
import {
  Building2, ShieldAlert, Plug, ScanLine,
  AlertTriangle, CheckCircle2, Clock, XCircle,
  TrendingUp, Eye
} from 'lucide-react'

interface WorkspaceCard {
  workspace: Workspace
  connectors: Connector[]
  totalAssets: number
  shadowAiCount: number
  highRiskCount: number
  lastScanAt?: string
  lastScanStatus?: string
}

const STATUS_BADGE: Record<string, { label: string; class: string }> = {
  active:   { label: 'Ativo',    class: 'bg-emerald-500/20 text-emerald-400' },
  paused:   { label: 'Pausado',  class: 'bg-amber-500/20 text-amber-400' },
  archived: { label: 'Arquivado', class: 'bg-slate-500/20 text-slate-400' },
}

// Backend stores last_scan_status as 'success' | 'error' | 'running' | null
const SCAN_BADGE: Record<string, { icon: React.ElementType; class: string; label: string }> = {
  success:   { icon: CheckCircle2, class: 'text-emerald-400',            label: 'Concluído' },
  completed: { icon: CheckCircle2, class: 'text-emerald-400',            label: 'Concluído' },
  running:   { icon: ScanLine,     class: 'text-blue-400 animate-pulse', label: 'Rodando' },
  error:     { icon: XCircle,      class: 'text-red-400',                label: 'Falhou' },
  failed:    { icon: XCircle,      class: 'text-red-400',                label: 'Falhou' },
  pending:   { icon: Clock,        class: 'text-slate-400',              label: 'Pendente' },
}

function fmtDate(iso?: string) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('pt-BR', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  })
}

export default function AdminDashboard() {
  const router = useRouter()
  const [cards, setCards] = useState<WorkspaceCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const user = getUser()
    if (!user) { router.push('/login'); return }
    if (!user.is_platform_admin) { router.push('/workspaces'); return }

    async function load() {
      try {
        const workspaces: Workspace[] = await listWorkspaces()
        const result: WorkspaceCard[] = await Promise.all(
          workspaces.map(async (ws) => {
            try {
              const [connectors, assets]: [Connector[], DiscoveredAsset[]] = await Promise.all([
                listConnectors(ws.id),
                listAssets(ws.id, { limit: 500 }),
              ])
              const shadowAiCount = assets.filter((a) => a.is_shadow_ai).length
              const highRiskCount = assets.filter(
                (a) => a.risk_level === 'high' || a.risk_level === 'critical'
              ).length
              const lastScan = connectors
                .filter((c) => c.last_scan_at)
                .sort((a, b) =>
                  new Date(b.last_scan_at!).getTime() - new Date(a.last_scan_at!).getTime()
                )[0]
              return {
                workspace: ws,
                connectors,
                totalAssets: assets.length,
                shadowAiCount,
                highRiskCount,
                lastScanAt: lastScan?.last_scan_at,
                lastScanStatus: lastScan?.last_scan_status,
              }
            } catch {
              return {
                workspace: ws,
                connectors: [],
                totalAssets: 0,
                shadowAiCount: 0,
                highRiskCount: 0,
              }
            }
          })
        )
        setCards(result)
      } catch (e: unknown) {
        setError('Erro ao carregar dados da plataforma.')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [router])

  // Platform-level KPIs
  const totalClients   = cards.length
  const activeClients  = cards.filter((c) => c.workspace.status === 'active').length
  const totalAssets    = cards.reduce((s, c) => s + c.totalAssets, 0)
  const totalShadow    = cards.reduce((s, c) => s + c.shadowAiCount, 0)
  const totalHighRisk  = cards.reduce((s, c) => s + c.highRiskCount, 0)
  const totalConnectors = cards.reduce((s, c) => s + c.connectors.length, 0)

  return (
    <AppShell>
      <div className="p-8 max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white">Admin Dashboard</h1>
          <p className="text-slate-400 mt-1">Visão consolidada de todos os clientes na plataforma</p>
        </div>

        {/* Platform KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
          {[
            { label: 'Clientes',     value: totalClients,    icon: Building2,    color: 'text-blue-400' },
            { label: 'Ativos',       value: activeClients,   icon: CheckCircle2, color: 'text-emerald-400' },
            { label: 'Assets IA',    value: totalAssets,     icon: TrendingUp,   color: 'text-violet-400' },
            { label: 'Shadow AI',    value: totalShadow,     icon: AlertTriangle,color: 'text-amber-400' },
            { label: 'Alto Risco',   value: totalHighRisk,   icon: ShieldAlert,  color: 'text-red-400' },
            { label: 'Conectores',   value: totalConnectors, icon: Plug,         color: 'text-cyan-400' },
          ].map(({ label, value, icon: Icon, color }) => (
            <div key={label} className="bg-slate-800 rounded-xl p-4 border border-slate-700/50">
              <div className={`${color} mb-2`}><Icon size={18} /></div>
              <p className="text-2xl font-bold text-white">{loading ? '—' : value}</p>
              <p className="text-xs text-slate-400 mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Client table */}
        <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-700/50 flex items-center justify-between">
            <h2 className="text-white font-semibold">Clientes</h2>
            <span className="text-slate-400 text-sm">{totalClients} cadastrados</span>
          </div>

          {loading ? (
            <div className="p-12 text-center text-slate-400">Carregando...</div>
          ) : cards.length === 0 ? (
            <div className="p-12 text-center text-slate-400">Nenhum cliente cadastrado.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/50 text-slate-400 text-xs uppercase tracking-wider">
                    <th className="px-6 py-3 text-left font-medium">Cliente</th>
                    <th className="px-6 py-3 text-left font-medium">Status</th>
                    <th className="px-6 py-3 text-right font-medium">Assets</th>
                    <th className="px-6 py-3 text-right font-medium">Shadow AI</th>
                    <th className="px-6 py-3 text-right font-medium">Alto Risco</th>
                    <th className="px-6 py-3 text-right font-medium">Conectores</th>
                    <th className="px-6 py-3 text-left font-medium">Último Scan</th>
                    <th className="px-6 py-3 text-center font-medium">Ação</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/30">
                  {cards.map(({ workspace: ws, connectors, totalAssets, shadowAiCount, highRiskCount, lastScanAt, lastScanStatus }) => {
                    const statusBadge = STATUS_BADGE[ws.status] ?? STATUS_BADGE.active
                    const scanBadge = lastScanStatus
                      ? (SCAN_BADGE[lastScanStatus] ?? SCAN_BADGE.pending)
                      : null

                    return (
                      <tr key={ws.id} className="hover:bg-slate-700/30 transition-colors">
                        <td className="px-6 py-4">
                          <div>
                            <p className="text-white font-medium">{ws.name}</p>
                            <p className="text-slate-400 text-xs">{ws.industry ?? ws.slug}</p>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusBadge.class}`}>
                            {statusBadge.label}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <span className="text-white font-medium">{totalAssets}</span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          {shadowAiCount > 0 ? (
                            <span className="text-amber-400 font-medium">{shadowAiCount}</span>
                          ) : (
                            <span className="text-slate-400">0</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-right">
                          {highRiskCount > 0 ? (
                            <span className="text-red-400 font-medium">{highRiskCount}</span>
                          ) : (
                            <span className="text-slate-400">0</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <span className="text-slate-300">{connectors.length}</span>
                        </td>
                        <td className="px-6 py-4">
                          {scanBadge ? (
                            <div className="flex items-center gap-1.5">
                              <scanBadge.icon size={13} className={scanBadge.class} />
                              <div>
                                <p className={`text-xs ${scanBadge.class}`}>{scanBadge.label}</p>
                                {lastScanAt && (
                                  <p className="text-slate-500 text-xs">{fmtDate(lastScanAt)}</p>
                                )}
                              </div>
                            </div>
                          ) : (
                            <span className="text-slate-500 text-xs">Sem scan</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-center">
                          <Link href={`/workspaces/${ws.id}`}
                            className="inline-flex items-center gap-1.5 text-xs text-brand-400 hover:text-brand-300 transition-colors font-medium">
                            <Eye size={13} />
                            Ver
                          </Link>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}
