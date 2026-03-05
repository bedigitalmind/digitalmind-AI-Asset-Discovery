'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import AppShell from '@/components/layout/AppShell'
import {
  getWorkspace, listAssets, updateAsset,
  getDetectionStats, getAssetCategories,
} from '@/lib/api'
import type { Workspace, DiscoveredAsset } from '@/types'
import {
  ShieldAlert, AlertTriangle, CheckCircle2, Eye, XCircle,
  Clock, Search, Filter, ChevronDown, X, Loader2,
  TrendingUp, BarChart3, Layers, RefreshCw,
} from 'lucide-react'

// ─── Constants ────────────────────────────────────────────────────────────────

const RISK_BADGE: Record<string, string> = {
  low:      'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  medium:   'bg-amber-500/15 text-amber-400 border-amber-500/30',
  high:     'bg-orange-500/15 text-orange-400 border-orange-500/30',
  critical: 'bg-red-500/15 text-red-400 border-red-500/30',
}

const ANALYST_STATUS_META: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  pending_review: { label: 'Revisão pendente', color: 'text-slate-300',   icon: Clock },
  confirmed:      { label: 'Confirmado',        color: 'text-emerald-400', icon: CheckCircle2 },
  false_positive: { label: 'Falso positivo',    color: 'text-slate-400',   icon: XCircle },
  accepted_risk:  { label: 'Risco aceito',      color: 'text-amber-400',   icon: ShieldAlert },
}

const CATEGORIES = [
  'Conversational AI', 'Copilots', 'AI Agents',
  'Embedded SaaS AI', 'ERP/CRM AI', 'AI APIs & SDKs',
  'Proprietary Models & Infrastructure',
]

function fmtDate(iso?: string) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('pt-BR', {
    day: '2-digit', month: 'short', year: 'numeric',
  })
}

// ─── Asset Detail Drawer ──────────────────────────────────────────────────────

interface DrawerProps {
  asset: DiscoveredAsset
  workspaceId: number
  onClose: () => void
  onUpdated: (updated: DiscoveredAsset) => void
}

function AssetDrawer({ asset, workspaceId, onClose, onUpdated }: DrawerProps) {
  const [status, setStatus] = useState(asset.analyst_status)
  const [notes, setNotes] = useState(asset.analyst_notes ?? '')
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    setSaving(true)
    try {
      const updated = await updateAsset(workspaceId, asset.id, {
        analyst_status: status,
        analyst_notes: notes,
      })
      onUpdated({ ...asset, ...updated })
      onClose()
    } catch {
      // keep drawer open on error
    } finally {
      setSaving(false)
    }
  }

  const statusMeta = ANALYST_STATUS_META[status] ?? ANALYST_STATUS_META.pending_review

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* Drawer */}
      <div className="w-[480px] bg-slate-800 border-l border-slate-700 flex flex-col h-full overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between px-6 py-5 border-b border-slate-700">
          <div className="flex-1 min-w-0 pr-4">
            <p className="text-slate-400 text-xs mb-1">{asset.category} · {asset.subcategory ?? ''}</p>
            <h2 className="text-white font-bold text-lg leading-tight truncate">{asset.name}</h2>
            {asset.vendor && <p className="text-slate-400 text-sm mt-0.5">{asset.vendor}</p>}
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors mt-1">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {/* Risk + Shadow AI */}
          <div className="flex items-center gap-3">
            <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium border ${RISK_BADGE[asset.risk_level] ?? RISK_BADGE.medium}`}>
              {asset.risk_level} · {asset.risk_score}/10
            </span>
            {asset.is_shadow_ai && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium bg-amber-500/15 text-amber-400 border border-amber-500/30">
                <AlertTriangle size={12} />
                Shadow AI
              </span>
            )}
            <span className="text-slate-400 text-xs ml-auto">
              Conf. {Math.round(asset.confidence_score * 100)}%
            </span>
          </div>

          {/* Description */}
          {asset.description && (
            <div>
              <p className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-2">Descrição</p>
              <p className="text-slate-300 text-sm leading-relaxed">{asset.description}</p>
            </div>
          )}

          {/* Metadata */}
          <div>
            <p className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-3">Detalhes</p>
            <dl className="space-y-2">
              {[
                ['Tipo de sinal', asset.resource_type],
                ['Grupo / Localização', asset.resource_group ?? asset.location],
                ['Primeiro visto', fmtDate(asset.first_seen_at)],
                ['Último visto', fmtDate(asset.last_seen_at)],
              ].filter(([, v]) => v).map(([label, value]) => (
                <div key={label as string} className="flex gap-3">
                  <dt className="text-slate-500 text-xs w-36 flex-shrink-0 pt-0.5">{label}</dt>
                  <dd className="text-slate-300 text-xs flex-1 break-all">{value}</dd>
                </div>
              ))}
            </dl>
          </div>

          {/* Analyst review */}
          <div>
            <p className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-3">Revisão do Analista</p>
            <div className="space-y-2">
              {Object.entries(ANALYST_STATUS_META).map(([key, meta]) => (
                <label key={key}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-all
                    ${status === key
                      ? 'border-brand-500 bg-brand-500/10'
                      : 'border-slate-700 hover:border-slate-600'}`}>
                  <input type="radio" name="status" value={key}
                    checked={status === key}
                    onChange={() => setStatus(key as DiscoveredAsset['analyst_status'])}
                    className="hidden" />
                  <meta.icon size={15} className={status === key ? meta.color : 'text-slate-500'} />
                  <span className={`text-sm ${status === key ? 'text-white' : 'text-slate-400'}`}>
                    {meta.label}
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* Notes */}
          <div>
            <p className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-2">Notas do Analista</p>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Adicione contexto, justificativa ou ações tomadas..."
              rows={4}
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2.5 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 resize-none"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-700 flex gap-3">
          <button onClick={onClose}
            className="flex-1 px-4 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-700 transition-colors">
            Cancelar
          </button>
          <button onClick={handleSave} disabled={saving}
            className="flex-1 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
            {saving && <Loader2 size={14} className="animate-spin" />}
            {saving ? 'Salvando...' : 'Salvar revisão'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

interface CategoryStat {
  category: string
  count: number
  shadow_count: number
  high_risk_count: number
  avg_risk_score: number
}

interface DetectionStats {
  total_assets: number
  shadow_ai: number
  high_risk: number
  critical_risk: number
  pending_review: number
  confirmed: number
  categories: number
  last_seen_at?: string
  category_breakdown: CategoryStat[]
}

export default function AssetsPage() {
  const params = useParams()
  const router = useRouter()
  const workspaceId = Number(params.id)

  const [workspace, setWorkspace]     = useState<Workspace | null>(null)
  const [assets, setAssets]           = useState<DiscoveredAsset[]>([])
  const [stats, setStats]             = useState<DetectionStats | null>(null)
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState('')
  const [selectedAsset, setSelectedAsset] = useState<DiscoveredAsset | null>(null)

  // Filters
  const [search, setSearch]           = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterRisk, setFilterRisk]   = useState('')
  const [filterShadow, setFilterShadow] = useState(false)
  const [filterStatus, setFilterStatus] = useState('')
  const [showFilters, setShowFilters] = useState(false)

  const load = useCallback(async () => {
    try {
      const [ws, assetList, detStats] = await Promise.all([
        getWorkspace(workspaceId),
        listAssets(workspaceId, { limit: 500 }),
        getDetectionStats(workspaceId),
      ])
      setWorkspace(ws)
      // Backend returns {total, items} or flat array
      setAssets(Array.isArray(assetList) ? assetList : (assetList.items ?? []))
      setStats(detStats)
    } catch {
      setError('Erro ao carregar assets.')
    } finally {
      setLoading(false)
    }
  }, [workspaceId])

  useEffect(() => {
    if (!workspaceId) { router.push('/workspaces'); return }
    load()
  }, [workspaceId, load, router])

  function handleAssetUpdated(updated: DiscoveredAsset) {
    setAssets((prev) => prev.map((a) => a.id === updated.id ? updated : a))
  }

  // Client-side filtering
  const filtered = assets.filter((a) => {
    if (search && !a.name.toLowerCase().includes(search.toLowerCase()) &&
        !(a.vendor ?? '').toLowerCase().includes(search.toLowerCase())) return false
    if (filterCategory && a.category !== filterCategory) return false
    if (filterRisk && a.risk_level !== filterRisk) return false
    if (filterShadow && !a.is_shadow_ai) return false
    if (filterStatus && a.analyst_status !== filterStatus) return false
    return true
  })

  const activeFilters = [filterCategory, filterRisk, filterStatus, filterShadow ? 'shadow' : ''].filter(Boolean).length

  return (
    <AppShell workspaceId={workspaceId} workspaceName={workspace?.name}>
      <div className="p-8 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white">Assets de IA</h1>
            <p className="text-slate-400 mt-1">
              {loading ? 'Carregando...' : `${assets.length} assets descobertos`}
              {stats?.last_seen_at && (
                <span className="ml-2 text-xs">· Atualizado {fmtDate(stats.last_seen_at)}</span>
              )}
            </p>
          </div>
          <button onClick={load} disabled={loading}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-700 transition-colors disabled:opacity-50">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Atualizar
          </button>
        </div>

        {/* KPI row */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 mb-8">
            {[
              { label: 'Total',          value: stats.total_assets,   color: 'text-white',        icon: Layers },
              { label: 'Shadow AI',      value: stats.shadow_ai,      color: 'text-amber-400',    icon: AlertTriangle },
              { label: 'Alto risco',     value: stats.high_risk,      color: 'text-orange-400',   icon: ShieldAlert },
              { label: 'Crítico',        value: stats.critical_risk,  color: 'text-red-400',      icon: ShieldAlert },
              { label: 'Pendente rev.',  value: stats.pending_review, color: 'text-slate-300',    icon: Clock },
              { label: 'Confirmados',    value: stats.confirmed,      color: 'text-emerald-400',  icon: CheckCircle2 },
              { label: 'Categorias',     value: stats.categories,     color: 'text-violet-400',   icon: BarChart3 },
            ].map(({ label, value, color, icon: Icon }) => (
              <div key={label} className="bg-slate-800 rounded-xl p-3.5 border border-slate-700/50">
                <Icon size={15} className={`${color} mb-2`} />
                <p className={`text-xl font-bold ${color}`}>{value ?? 0}</p>
                <p className="text-slate-500 text-xs mt-0.5">{label}</p>
              </div>
            ))}
          </div>
        )}

        {/* Category breakdown bar */}
        {stats?.category_breakdown && stats.category_breakdown.length > 0 && (
          <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-5 mb-6">
            <p className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-4">Por categoria</p>
            <div className="space-y-2.5">
              {stats.category_breakdown.map((cat) => (
                <div key={cat.category} className="flex items-center gap-3">
                  <button
                    onClick={() => setFilterCategory(filterCategory === cat.category ? '' : cat.category)}
                    className={`text-xs w-52 text-left truncate transition-colors
                      ${filterCategory === cat.category ? 'text-brand-400 font-medium' : 'text-slate-400 hover:text-slate-200'}`}
                  >
                    {cat.category}
                  </button>
                  <div className="flex-1 bg-slate-700 rounded-full h-1.5 overflow-hidden">
                    <div
                      className="h-full bg-brand-500 rounded-full transition-all"
                      style={{ width: `${Math.max(2, (cat.count / (stats.total_assets || 1)) * 100)}%` }}
                    />
                  </div>
                  <span className="text-slate-300 text-xs w-8 text-right">{cat.count}</span>
                  {cat.shadow_count > 0 && (
                    <span className="text-amber-400 text-xs w-16 text-right">
                      {cat.shadow_count} shadow
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Search + filters */}
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-md">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por nome ou vendor..."
              className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50"
            />
            {search && (
              <button onClick={() => setSearch('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white">
                <X size={13} />
              </button>
            )}
          </div>

          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-colors
              ${showFilters || activeFilters > 0
                ? 'border-brand-500 bg-brand-500/10 text-brand-400'
                : 'border-slate-600 text-slate-400 hover:text-slate-200 hover:border-slate-500'}`}
          >
            <Filter size={14} />
            Filtros
            {activeFilters > 0 && (
              <span className="bg-brand-500 text-white text-xs rounded-full px-1.5 py-0 leading-5 min-w-[18px] text-center">
                {activeFilters}
              </span>
            )}
            <ChevronDown size={13} className={showFilters ? 'rotate-180 transition-transform' : 'transition-transform'} />
          </button>

          <span className="text-slate-400 text-sm ml-auto">
            {filtered.length} de {assets.length}
          </span>
        </div>

        {/* Filter panel */}
        {showFilters && (
          <div className="bg-slate-800 rounded-xl border border-slate-700/50 p-4 mb-4 flex flex-wrap gap-4">
            {/* Category */}
            <div className="min-w-48">
              <label className="block text-slate-400 text-xs mb-1.5">Categoria</label>
              <select
                value={filterCategory}
                onChange={(e) => setFilterCategory(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                <option value="">Todas</option>
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            {/* Risk */}
            <div className="min-w-36">
              <label className="block text-slate-400 text-xs mb-1.5">Risco</label>
              <select
                value={filterRisk}
                onChange={(e) => setFilterRisk(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                <option value="">Todos</option>
                <option value="low">Baixo</option>
                <option value="medium">Médio</option>
                <option value="high">Alto</option>
                <option value="critical">Crítico</option>
              </select>
            </div>

            {/* Analyst status */}
            <div className="min-w-44">
              <label className="block text-slate-400 text-xs mb-1.5">Status analista</label>
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:ring-1 focus:ring-brand-500"
              >
                <option value="">Todos</option>
                {Object.entries(ANALYST_STATUS_META).map(([key, { label }]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </div>

            {/* Shadow AI toggle */}
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 cursor-pointer">
                <div
                  onClick={() => setFilterShadow(!filterShadow)}
                  className={`w-9 h-5 rounded-full transition-colors relative ${filterShadow ? 'bg-amber-500' : 'bg-slate-600'}`}
                >
                  <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${filterShadow ? 'translate-x-4' : 'translate-x-0.5'}`} />
                </div>
                <span className="text-slate-300 text-sm">Somente Shadow AI</span>
              </label>
            </div>

            {/* Clear */}
            {activeFilters > 0 && (
              <button
                onClick={() => { setFilterCategory(''); setFilterRisk(''); setFilterStatus(''); setFilterShadow(false) }}
                className="flex items-end pb-1 text-xs text-slate-400 hover:text-white transition-colors gap-1"
              >
                <X size={12} /> Limpar filtros
              </button>
            )}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-4 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="text-center py-20 text-slate-400">
            <Loader2 size={28} className="animate-spin mx-auto mb-3" />
            Carregando assets...
          </div>
        )}

        {/* Empty state */}
        {!loading && assets.length === 0 && (
          <div className="bg-slate-800 rounded-2xl border border-dashed border-slate-600 p-16 text-center">
            <div className="w-14 h-14 bg-slate-700 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <TrendingUp size={24} className="text-slate-400" />
            </div>
            <h3 className="text-white font-semibold text-lg mb-2">Nenhum asset descoberto</h3>
            <p className="text-slate-400 text-sm max-w-sm mx-auto">
              Configure um conector e execute um scan, ou faça upload de logs na aba Ingestão de Dados para começar a descoberta.
            </p>
          </div>
        )}

        {/* No results after filter */}
        {!loading && assets.length > 0 && filtered.length === 0 && (
          <div className="text-center py-12 text-slate-400">
            Nenhum asset com os filtros aplicados.{' '}
            <button onClick={() => { setSearch(''); setFilterCategory(''); setFilterRisk(''); setFilterStatus(''); setFilterShadow(false) }}
              className="text-brand-400 hover:text-brand-300 underline">
              Limpar filtros
            </button>
          </div>
        )}

        {/* Assets table */}
        {!loading && filtered.length > 0 && (
          <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700/50 text-xs text-slate-400 uppercase tracking-wider">
                    <th className="px-5 py-3.5 text-left font-medium">Asset</th>
                    <th className="px-5 py-3.5 text-left font-medium">Categoria</th>
                    <th className="px-5 py-3.5 text-left font-medium">Risco</th>
                    <th className="px-5 py-3.5 text-left font-medium">Shadow AI</th>
                    <th className="px-5 py-3.5 text-left font-medium">Status</th>
                    <th className="px-5 py-3.5 text-left font-medium">Visto em</th>
                    <th className="px-5 py-3.5 text-center font-medium">Revisar</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/30">
                  {filtered.map((asset) => {
                    const statusMeta = ANALYST_STATUS_META[asset.analyst_status] ?? ANALYST_STATUS_META.pending_review
                    const StatusIcon = statusMeta.icon
                    return (
                      <tr key={asset.id}
                        className="hover:bg-slate-700/30 transition-colors cursor-pointer"
                        onClick={() => setSelectedAsset(asset)}>
                        <td className="px-5 py-3.5">
                          <div>
                            <p className="text-white font-medium">{asset.name}</p>
                            {asset.vendor && <p className="text-slate-400 text-xs">{asset.vendor}</p>}
                          </div>
                        </td>
                        <td className="px-5 py-3.5">
                          <p className="text-slate-300 text-xs">{asset.category}</p>
                          {asset.subcategory && <p className="text-slate-500 text-xs">{asset.subcategory}</p>}
                        </td>
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-2">
                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${RISK_BADGE[asset.risk_level] ?? RISK_BADGE.medium}`}>
                              {asset.risk_level}
                            </span>
                            <span className="text-slate-500 text-xs">{asset.risk_score}/10</span>
                          </div>
                        </td>
                        <td className="px-5 py-3.5">
                          {asset.is_shadow_ai
                            ? <span className="flex items-center gap-1 text-amber-400 text-xs font-medium"><AlertTriangle size={11} />Shadow AI</span>
                            : <span className="text-slate-500 text-xs">—</span>
                          }
                        </td>
                        <td className="px-5 py-3.5">
                          <span className={`flex items-center gap-1.5 text-xs ${statusMeta.color}`}>
                            <StatusIcon size={12} />
                            {statusMeta.label}
                          </span>
                        </td>
                        <td className="px-5 py-3.5 text-slate-400 text-xs">
                          {fmtDate(asset.last_seen_at)}
                        </td>
                        <td className="px-5 py-3.5 text-center">
                          <button
                            onClick={(e) => { e.stopPropagation(); setSelectedAsset(asset) }}
                            className="text-brand-400 hover:text-brand-300 transition-colors"
                            title="Abrir detalhes"
                          >
                            <Eye size={15} />
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Detail drawer */}
      {selectedAsset && (
        <AssetDrawer
          asset={selectedAsset}
          workspaceId={workspaceId}
          onClose={() => setSelectedAsset(null)}
          onUpdated={handleAssetUpdated}
        />
      )}
    </AppShell>
  )
}
