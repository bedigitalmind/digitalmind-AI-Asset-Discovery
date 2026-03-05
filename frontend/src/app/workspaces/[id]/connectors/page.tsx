'use client'
import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import AppShell from '@/components/layout/AppShell'
import { getWorkspace, listConnectors, createConnector, triggerScan, listAssets } from '@/lib/api'
import type { Workspace, Connector, DiscoveredAsset } from '@/types'
import {
  Plug, Plus, ScanLine, CheckCircle2, XCircle, Clock,
  AlertTriangle, ShieldAlert, RefreshCw, ChevronDown,
  ChevronRight, Eye, X, Loader2
} from 'lucide-react'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(iso?: string) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('pt-BR', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function fmtBytes(bytes: number) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

const RISK_BADGE: Record<string, string> = {
  low:      'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  medium:   'bg-amber-500/15 text-amber-400 border-amber-500/30',
  high:     'bg-orange-500/15 text-orange-400 border-orange-500/30',
  critical: 'bg-red-500/15 text-red-400 border-red-500/30',
}

// Backend returns 'success' | 'error' | 'running' | null; we map to display labels
const STATUS_BADGE: Record<string, { icon: React.ElementType; class: string; label: string }> = {
  success:   { icon: CheckCircle2, class: 'text-emerald-400',            label: 'Concluído' },
  completed: { icon: CheckCircle2, class: 'text-emerald-400',            label: 'Concluído' },
  running:   { icon: ScanLine,     class: 'text-blue-400',               label: 'Rodando' },
  error:     { icon: XCircle,      class: 'text-red-400',                label: 'Falhou' },
  failed:    { icon: XCircle,      class: 'text-red-400',                label: 'Falhou' },
  pending:   { icon: Clock,        class: 'text-slate-400',              label: 'Pendente' },
}

const ANALYST_STATUS_LABELS: Record<string, string> = {
  pending_review: 'Revisão pendente',
  confirmed:      'Confirmado',
  false_positive: 'Falso positivo',
  accepted_risk:  'Risco aceito',
}

type ConnectorPlatform =
  | 'azure' | 'm365'
  | 'salesforce' | 'servicenow' | 'sap' | 'dynamics365'
  | 'manual'

interface ConnectorField { key: string; label: string; placeholder: string; secret?: boolean; hint?: string }
interface ConnectorTypeMeta { label: string; color: string; hint: string; fields: ConnectorField[] }

const CONNECTOR_TYPE_META: Record<ConnectorPlatform, ConnectorTypeMeta> = {
  azure: {
    label: 'Microsoft Azure',
    color: 'text-blue-400',
    hint: 'App Registration no Azure AD com permissão de leitura na subscription.',
    fields: [
      { key: 'tenant_id',       label: 'Tenant ID',       placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
      { key: 'client_id',       label: 'Client ID',       placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
      { key: 'client_secret',   label: 'Client Secret',   placeholder: 'Credencial do App Registration', secret: true },
      { key: 'subscription_id', label: 'Subscription ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
    ],
  },
  m365: {
    label: 'Microsoft 365',
    color: 'text-violet-400',
    hint: 'App Registration no Azure AD com permissões de aplicação: Reports.Read.All · Organization.Read.All · TeamsApp.Read.All · Application.Read.All. Descobre Copilot M365, Teams AI apps, app registrations com IA e service principals Azure AI.',
    fields: [
      { key: 'tenant_id',     label: 'Tenant ID',          placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
      { key: 'client_id',     label: 'Client ID',          placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
      { key: 'client_secret', label: 'Client Secret',      placeholder: 'Credencial do App Registration', secret: true },
      { key: 'include_beta',  label: 'Endpoints beta Graph', placeholder: 'true — habilita SharePoint Syntex e Copilot Studio' },
    ],
  },
  salesforce: {
    label: 'Salesforce',
    color: 'text-sky-400',
    hint: 'Connected App com "Client Credentials Flow" habilitado. Descobre Einstein AI, Agentforce, ML Models e pacotes AppExchange com IA.',
    fields: [
      { key: 'instance_url',  label: 'Instance URL',   placeholder: 'https://mycompany.my.salesforce.com' },
      { key: 'client_id',     label: 'Consumer Key',   placeholder: 'Connected App Consumer Key' },
      { key: 'client_secret', label: 'Consumer Secret', placeholder: 'Connected App Consumer Secret', secret: true },
    ],
  },
  servicenow: {
    label: 'ServiceNow',
    color: 'text-emerald-400',
    hint: 'Conta de serviço com leitura nas tabelas de AI Platform. Descobre Virtual Agent, Now Intelligence e ML Solutions.',
    fields: [
      { key: 'instance_url', label: 'Instance URL', placeholder: 'https://mycompany.service-now.com' },
      { key: 'username',     label: 'Username',     placeholder: 'svc_ai_discovery' },
      { key: 'password',     label: 'Password',     placeholder: 'Senha da conta de serviço', secret: true },
    ],
  },
  sap: {
    label: 'SAP AI Core',
    color: 'text-amber-400',
    hint: 'Service Key do SAP BTP (XSUAA). Descobre deployments e cenários no SAP AI Core, SAP Joule e serviços BTP AI.',
    fields: [
      { key: 'token_url',       label: 'Token URL (XSUAA)',   placeholder: 'https://my-subaccount.authentication.eu10.hana.ondemand.com/oauth/token' },
      { key: 'client_id',       label: 'Client ID',           placeholder: 'sb-my-service!b12345' },
      { key: 'client_secret',   label: 'Client Secret',       placeholder: 'Credencial da service key SAP BTP', secret: true },
      { key: 'ai_core_api_url', label: 'AI Core API URL',     placeholder: 'https://api.ai.prod.eu-central-1.aws.ml.hana.ondemand.com' },
      { key: 'resource_group',  label: 'Resource Group',      placeholder: 'default' },
    ],
  },
  dynamics365: {
    label: 'Dynamics 365',
    color: 'text-rose-400',
    hint: 'App Registration no Azure AD com permissão "Dynamics CRM user_impersonation". Descobre Copilot, Power Virtual Agents e AI Builder.',
    fields: [
      { key: 'tenant_id',       label: 'Tenant ID',          placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
      { key: 'client_id',       label: 'Client ID',          placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' },
      { key: 'client_secret',   label: 'Client Secret',      placeholder: 'Credencial do App Registration', secret: true },
      { key: 'environment_url', label: 'Environment URL',    placeholder: 'https://myorg.crm.dynamics.com' },
    ],
  },
  manual: {
    label: 'Manual / Upload',
    color: 'text-slate-400',
    hint: '',
    fields: [],
  },
}

// ─── Add Connector Modal ──────────────────────────────────────────────────────

interface AddConnectorModalProps {
  workspaceId: number
  onClose: () => void
  onCreated: () => void
}

function AddConnectorModal({ workspaceId, onClose, onCreated }: AddConnectorModalProps) {
  const [name, setName] = useState('')
  const [connectorType, setConnectorType] = useState<ConnectorPlatform>('azure')
  const [config, setConfig] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const meta = CONNECTOR_TYPE_META[connectorType]

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) { setError('Nome é obrigatório.'); return }
    setSaving(true)
    setError('')
    try {
      await createConnector(workspaceId, {
        name: name.trim(),
        connector_type: connectorType,
        platform: connectorType,
        config,
      })
      onCreated()
      onClose()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? 'Erro ao criar conector.'
      setError(msg)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-800 rounded-2xl border border-slate-700 w-full max-w-lg shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-slate-700">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-brand-500/20 rounded-lg flex items-center justify-center">
              <Plug size={16} className="text-brand-400" />
            </div>
            <h2 className="text-white font-semibold">Novo Conector</h2>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {/* Name */}
          <div>
            <label className="block text-slate-300 text-sm font-medium mb-1.5">Nome do conector</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex: Azure Produção"
              className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50"
            />
          </div>

          {/* Type */}
          <div>
            <label className="block text-slate-300 text-sm font-medium mb-1.5">Tipo de conector</label>
            <div className="grid grid-cols-2 gap-2">
              {(Object.keys(CONNECTOR_TYPE_META) as ConnectorPlatform[]).map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => { setConnectorType(type); setConfig({}) }}
                  className={`px-3 py-2.5 rounded-lg border text-sm font-medium transition-all text-left
                    ${connectorType === type
                      ? 'border-brand-500 bg-brand-500/10 text-white'
                      : 'border-slate-600 text-slate-400 hover:border-slate-500 hover:text-slate-300'}`}
                >
                  <span className={connectorType === type ? 'text-white' : CONNECTOR_TYPE_META[type].color}>
                    {CONNECTOR_TYPE_META[type].label}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Dynamic config fields */}
          {meta.fields.length > 0 && (
            <div className="space-y-3">
              {meta.hint && (
                <p className="text-slate-400 text-xs bg-slate-900/50 rounded-lg px-3 py-2 border border-slate-700/50">
                  {meta.hint}
                </p>
              )}
              {meta.fields.map((field) => (
                <div key={field.key}>
                  <label className="block text-slate-300 text-xs font-medium mb-1">{field.label}</label>
                  <input
                    type={field.secret ? 'password' : 'text'}
                    value={config[field.key] ?? ''}
                    onChange={(e) => setConfig((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    placeholder={field.placeholder}
                    className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-brand-500/50 font-mono text-xs"
                  />
                </div>
              ))}
            </div>
          )}

          {meta.fields.length === 0 && connectorType === 'manual' && (
            <p className="text-slate-400 text-sm bg-slate-900/50 rounded-lg p-3 border border-slate-700">
              O conector manual não requer credenciais. Assets serão descobertos via upload de arquivos na aba <strong className="text-slate-300">Ingestão de Dados</strong>.
            </p>
          )}

          {error && (
            <p className="text-red-400 text-sm bg-red-500/10 rounded-lg px-3 py-2 border border-red-500/20">
              {error}
            </p>
          )}

          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 px-4 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-700 transition-colors">
              Cancelar
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
              {saving && <Loader2 size={14} className="animate-spin" />}
              {saving ? 'Salvando...' : 'Criar Conector'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ─── Asset Table ──────────────────────────────────────────────────────────────

function AssetTable({ assets }: { assets: DiscoveredAsset[] }) {
  const [expanded, setExpanded] = useState(true)
  const [filter, setFilter] = useState<string>('all')

  const filtered = filter === 'all' ? assets
    : filter === 'shadow' ? assets.filter((a) => a.is_shadow_ai)
    : assets.filter((a) => a.risk_level === filter)

  return (
    <div className="bg-slate-800/50 rounded-xl border border-slate-700/50">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-slate-700/20 transition-colors rounded-t-xl"
      >
        <div className="flex items-center gap-3">
          {expanded ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
          <span className="text-white font-medium text-sm">Assets Descobertos</span>
          <span className="bg-slate-700 text-slate-300 text-xs px-2 py-0.5 rounded-full">{assets.length}</span>
        </div>
        <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
          {['all', 'shadow', 'high', 'critical'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors
                ${filter === f
                  ? 'border-brand-500 bg-brand-500/10 text-brand-400'
                  : 'border-slate-600 text-slate-400 hover:text-slate-300'}`}
            >
              {f === 'all' ? 'Todos' : f === 'shadow' ? 'Shadow AI' : f === 'high' ? 'Alto risco' : 'Crítico'}
            </button>
          ))}
        </div>
      </button>

      {expanded && (
        <div className="overflow-x-auto">
          {filtered.length === 0 ? (
            <div className="px-5 pb-5 text-slate-500 text-sm text-center py-8">
              Nenhum asset encontrado com este filtro.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-t border-slate-700/50 text-xs text-slate-400 uppercase tracking-wider">
                  <th className="px-5 py-3 text-left font-medium">Asset</th>
                  <th className="px-5 py-3 text-left font-medium">Categoria</th>
                  <th className="px-5 py-3 text-left font-medium">Risco</th>
                  <th className="px-5 py-3 text-left font-medium">Shadow AI</th>
                  <th className="px-5 py-3 text-left font-medium">Status Analista</th>
                  <th className="px-5 py-3 text-left font-medium">Visto em</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/30">
                {filtered.map((asset) => (
                  <tr key={asset.id} className="hover:bg-slate-700/20 transition-colors">
                    <td className="px-5 py-3">
                      <div>
                        <p className="text-white font-medium text-sm">{asset.name}</p>
                        {asset.vendor && <p className="text-slate-400 text-xs">{asset.vendor}</p>}
                        {asset.resource_group && (
                          <p className="text-slate-500 text-xs font-mono">{asset.resource_group}</p>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <div>
                        <p className="text-slate-300 text-xs">{asset.category}</p>
                        {asset.subcategory && (
                          <p className="text-slate-500 text-xs">{asset.subcategory}</p>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${RISK_BADGE[asset.risk_level] ?? RISK_BADGE.low}`}>
                          {asset.risk_level}
                        </span>
                        <span className="text-slate-400 text-xs">{asset.risk_score}/10</span>
                      </div>
                    </td>
                    <td className="px-5 py-3">
                      {asset.is_shadow_ai ? (
                        <span className="flex items-center gap-1.5 text-amber-400 text-xs font-medium">
                          <AlertTriangle size={12} /> Shadow AI
                        </span>
                      ) : (
                        <span className="text-slate-500 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <span className={`text-xs ${
                        asset.analyst_status === 'confirmed' ? 'text-emerald-400'
                        : asset.analyst_status === 'false_positive' ? 'text-slate-400'
                        : asset.analyst_status === 'accepted_risk' ? 'text-amber-400'
                        : 'text-slate-300'
                      }`}>
                        {ANALYST_STATUS_LABELS[asset.analyst_status] ?? asset.analyst_status}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <p className="text-slate-400 text-xs">{fmtDate(asset.last_seen_at)}</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Connector Card ───────────────────────────────────────────────────────────

interface ConnectorCardProps {
  connector: Connector
  workspaceId: number
  assets: DiscoveredAsset[]
  onScan: (id: number) => void
  scanning: boolean
}

function ConnectorCard({ connector, workspaceId, assets, onScan, scanning }: ConnectorCardProps) {
  const meta = CONNECTOR_TYPE_META[connector.connector_type] ?? CONNECTOR_TYPE_META.manual
  const scanBadge = connector.last_scan_status
    ? (STATUS_BADGE[connector.last_scan_status] ?? STATUS_BADGE.pending)
    : null

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700/50 overflow-hidden">
      {/* Card header */}
      <div className="p-5 border-b border-slate-700/50">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-slate-700 rounded-lg flex items-center justify-center">
              <Plug size={16} className={meta.color} />
            </div>
            <div>
              <h3 className="text-white font-semibold">{connector.name}</h3>
              <p className={`text-xs ${meta.color}`}>{meta.label}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {connector.status === 'disabled' && (
              <span className="text-xs bg-slate-700 text-slate-400 px-2 py-0.5 rounded-full">Inativo</span>
            )}
            {connector.status === 'error' && (
              <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded-full border border-red-500/30">Erro</span>
            )}
            <button
              onClick={() => onScan(connector.id)}
              disabled={scanning || connector.last_scan_status === 'running'}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 hover:bg-brand-500 text-white text-xs font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {scanning ? (
                <><Loader2 size={12} className="animate-spin" /> Iniciando...</>
              ) : connector.last_scan_status === 'running' ? (
                <><ScanLine size={12} className="animate-pulse" /> Rodando...</>
              ) : (
                <><RefreshCw size={12} /> Escanear</>
              )}
            </button>
          </div>
        </div>

        {/* Scan status + stats */}
        <div className="mt-4 grid grid-cols-3 gap-3">
          <div className="bg-slate-900/50 rounded-lg p-3">
            <p className="text-slate-400 text-xs mb-1">Assets encontrados</p>
            <p className="text-white font-bold text-lg">{assets.length}</p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-3">
            <p className="text-slate-400 text-xs mb-1">Shadow AI</p>
            <p className="text-amber-400 font-bold text-lg">{assets.filter((a) => a.is_shadow_ai).length}</p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-3">
            <p className="text-slate-400 text-xs mb-1">Alto risco</p>
            <p className="text-red-400 font-bold text-lg">
              {assets.filter((a) => a.risk_level === 'high' || a.risk_level === 'critical').length}
            </p>
          </div>
        </div>

        {/* Last scan info */}
        {scanBadge && (
          <div className="mt-3 flex items-center gap-2">
            <scanBadge.icon size={13} className={scanBadge.class} />
            <span className={`text-xs ${scanBadge.class}`}>{scanBadge.label}</span>
            {connector.last_scan_at && (
              <span className="text-slate-500 text-xs">· {fmtDate(connector.last_scan_at)}</span>
            )}
          </div>
        )}
      </div>

      {/* Asset table */}
      <div className="p-4">
        <AssetTable assets={assets} />
      </div>
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function ConnectorsPage() {
  const params = useParams()
  const router = useRouter()
  const workspaceId = Number(params.id)

  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [connectors, setConnectors] = useState<Connector[]>([])
  const [allAssets, setAllAssets] = useState<DiscoveredAsset[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [scanningId, setScanningId] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      const [ws, conns, assets] = await Promise.all([
        getWorkspace(workspaceId),
        listConnectors(workspaceId),
        listAssets(workspaceId, { limit: 1000 }),
      ])
      setWorkspace(ws)
      setConnectors(conns)
      setAllAssets(assets)
    } catch {
      setError('Erro ao carregar conectores.')
    } finally {
      setLoading(false)
    }
  }, [workspaceId])

  useEffect(() => {
    if (!workspaceId) { router.push('/workspaces'); return }
    load()
  }, [workspaceId, load, router])

  // Poll while a scan is running
  useEffect(() => {
    const running = connectors.some((c) => c.last_scan_status === 'running')
    if (!running) return
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [connectors, load])

  async function handleScan(connectorId: number) {
    setScanningId(connectorId)
    try {
      await triggerScan(workspaceId, connectorId)
      await load()
    } catch {
      setError('Erro ao iniciar scan. Verifique as credenciais do conector.')
    } finally {
      setScanningId(null)
    }
  }

  // Assets per connector
  function getConnectorAssets(connectorId: number) {
    return allAssets.filter((a) => a.scan_job_id !== undefined)
    // In a real app we'd store connector_id in assets; for now return all
    // (scan_job → connector relationship is in the DB)
  }

  const totalShadow   = allAssets.filter((a) => a.is_shadow_ai).length
  const totalHighRisk = allAssets.filter((a) => a.risk_level === 'high' || a.risk_level === 'critical').length

  return (
    <AppShell workspaceId={workspaceId} workspaceName={workspace?.name}>
      <div className="p-8 max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white">Conectores</h1>
            <p className="text-slate-400 mt-1">Integre fontes de dados para descoberta automática de assets de IA</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <Plus size={16} />
            Novo Conector
          </button>
        </div>

        {/* Summary KPIs */}
        {!loading && allAssets.length > 0 && (
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="bg-slate-800 rounded-xl p-4 border border-slate-700/50">
              <div className="text-violet-400 mb-2"><Eye size={18} /></div>
              <p className="text-2xl font-bold text-white">{allAssets.length}</p>
              <p className="text-xs text-slate-400 mt-0.5">Total de assets</p>
            </div>
            <div className="bg-slate-800 rounded-xl p-4 border border-slate-700/50">
              <div className="text-amber-400 mb-2"><AlertTriangle size={18} /></div>
              <p className="text-2xl font-bold text-amber-400">{totalShadow}</p>
              <p className="text-xs text-slate-400 mt-0.5">Shadow AI detectado</p>
            </div>
            <div className="bg-slate-800 rounded-xl p-4 border border-slate-700/50">
              <div className="text-red-400 mb-2"><ShieldAlert size={18} /></div>
              <p className="text-2xl font-bold text-red-400">{totalHighRisk}</p>
              <p className="text-xs text-slate-400 mt-0.5">Assets alto/crítico risco</p>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 text-red-400 text-sm flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError('')}><X size={14} /></button>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="text-center py-20 text-slate-400">
            <Loader2 size={28} className="animate-spin mx-auto mb-3" />
            Carregando conectores...
          </div>
        )}

        {/* Empty state */}
        {!loading && connectors.length === 0 && (
          <div className="bg-slate-800 rounded-2xl border border-dashed border-slate-600 p-16 text-center">
            <div className="w-14 h-14 bg-slate-700 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <Plug size={24} className="text-slate-400" />
            </div>
            <h3 className="text-white font-semibold text-lg mb-2">Nenhum conector configurado</h3>
            <p className="text-slate-400 text-sm max-w-sm mx-auto mb-6">
              Adicione um conector para começar a escanear automaticamente a infraestrutura e descobrir assets de IA.
            </p>
            <button
              onClick={() => setShowModal(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <Plus size={16} />
              Adicionar primeiro conector
            </button>
          </div>
        )}

        {/* Connector cards */}
        {!loading && connectors.length > 0 && (
          <div className="space-y-6">
            {connectors.map((connector) => (
              <ConnectorCard
                key={connector.id}
                connector={connector}
                workspaceId={workspaceId}
                assets={allAssets}
                onScan={handleScan}
                scanning={scanningId === connector.id}
              />
            ))}
          </div>
        )}
      </div>

      {/* Add Connector Modal */}
      {showModal && (
        <AddConnectorModal
          workspaceId={workspaceId}
          onClose={() => setShowModal(false)}
          onCreated={load}
        />
      )}
    </AppShell>
  )
}
