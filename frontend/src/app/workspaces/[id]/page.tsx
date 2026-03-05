'use client'
import { useEffect, useState, useCallback } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import {
  getWorkspace, listFiles, listAuditLogs,
  getDetectionStats, triggerFileDetection,
} from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import AppShell from '@/components/layout/AppShell'
import type { Workspace, IngestionFile, AuditLog } from '@/types'
import {
  Upload, FileText, AlertTriangle, Activity, Clock,
  ShieldAlert, TrendingUp, Play, Loader2, CheckCircle2,
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { ptBR } from 'date-fns/locale'

interface DetectionStats {
  total_assets: number
  shadow_ai: number
  high_risk: number
  critical_risk: number
  pending_review: number
  last_seen_at?: string
}

function KpiCard({ label, value, icon: Icon, color, href }: {
  label: string; value: string | number; icon: React.ElementType; color: string; href?: string
}) {
  const content = (
    <div className={`bg-slate-800 border border-slate-700 rounded-xl p-5 ${href ? 'hover:border-slate-500 transition-colors' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <p className="text-slate-400 text-sm">{label}</p>
        <div className={`w-8 h-8 rounded-lg ${color} flex items-center justify-center`}>
          <Icon size={15} />
        </div>
      </div>
      <p className="text-2xl font-bold text-white">{value}</p>
    </div>
  )
  return href ? <Link href={href}>{content}</Link> : content
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const FILE_STATUS_STYLE: Record<string, string> = {
  uploaded:   'bg-slate-500/20 text-slate-400',
  processing: 'bg-blue-500/20 text-blue-400',
  processed:  'bg-emerald-500/20 text-emerald-400',
  error:      'bg-red-500/20 text-red-400',
}

const FILE_STATUS_LABEL: Record<string, string> = {
  uploaded:   'Aguardando',
  processing: 'Processando',
  processed:  'Processado',
  error:      'Erro',
}

export default function WorkspaceDashboard() {
  const router = useRouter()
  const params = useParams()
  const id = Number(params.id)

  const [workspace, setWorkspace]   = useState<Workspace | null>(null)
  const [files, setFiles]           = useState<IngestionFile[]>([])
  const [logs, setLogs]             = useState<AuditLog[]>([])
  const [stats, setStats]           = useState<DetectionStats | null>(null)
  const [loading, setLoading]       = useState(true)
  const [detectingId, setDetectingId] = useState<number | null>(null)
  const [detectMsg, setDetectMsg]   = useState('')

  const load = useCallback(async () => {
    try {
      const [ws, filesRes, logsRes, detStats] = await Promise.all([
        getWorkspace(id),
        listFiles(id).catch(() => []),
        listAuditLogs(id).catch(() => []),
        getDetectionStats(id).catch(() => null),
      ])
      setWorkspace(ws)
      setFiles(Array.isArray(filesRes) ? filesRes : (filesRes.items ?? []))
      setLogs(Array.isArray(logsRes) ? logsRes : (logsRes.items ?? []))
      setStats(detStats)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    load()
  }, [id, router, load])

  async function handleDetect(fileId: number) {
    setDetectingId(fileId)
    setDetectMsg('')
    try {
      await triggerFileDetection(id, fileId)
      setDetectMsg('Detecção iniciada em background. Assets aparecerão em alguns instantes.')
      await load()
    } catch {
      setDetectMsg('Erro ao iniciar detecção.')
    } finally {
      setDetectingId(null)
    }
  }

  if (loading) return (
    <AppShell>
      <div className="flex items-center justify-center h-64 text-slate-400">Carregando...</div>
    </AppShell>
  )

  const pendingFiles = files.filter((f) => f.status === 'uploaded')

  return (
    <AppShell workspaceId={id} workspaceName={workspace?.name}>
      <div className="p-8 max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white">{workspace?.name}</h1>
          <p className="text-slate-400 mt-1 text-sm">
            {workspace?.industry && `${workspace.industry} · `}
            {workspace?.company_size && `${workspace.company_size} · `}
            Workspace <code className="bg-slate-700 px-1.5 py-0.5 rounded text-xs">{workspace?.slug}</code>
          </p>
        </div>

        {/* Detection banner for pending files */}
        {pendingFiles.length > 0 && (
          <div className="bg-brand-500/10 border border-brand-500/30 rounded-xl p-4 mb-6 flex items-center justify-between">
            <div>
              <p className="text-white font-medium text-sm">
                {pendingFiles.length} {pendingFiles.length === 1 ? 'arquivo pronto' : 'arquivos prontos'} para análise
              </p>
              <p className="text-slate-400 text-xs mt-0.5">
                Execute a detecção para identificar assets de IA automaticamente
              </p>
            </div>
            <Link href={`/workspaces/${id}/ingest`}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 hover:bg-brand-500 text-white text-xs font-medium rounded-lg transition-colors">
              <Play size={12} /> Ir para ingestão
            </Link>
          </div>
        )}

        {detectMsg && (
          <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-3 mb-6 flex items-center gap-2 text-emerald-400 text-sm">
            <CheckCircle2 size={15} />
            {detectMsg}
          </div>
        )}

        {/* KPI Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <KpiCard label="Arquivos Ingeridos" value={files.length}
            icon={FileText} color="bg-brand-500/20 text-brand-500"
            href={`/workspaces/${id}/ingest`} />
          <KpiCard
            label="Assets de IA"
            value={stats?.total_assets ?? '—'}
            icon={TrendingUp}
            color="bg-violet-500/20 text-violet-400"
            href={`/workspaces/${id}/assets`}
          />
          <KpiCard
            label="Shadow AI"
            value={stats?.shadow_ai ?? '—'}
            icon={AlertTriangle}
            color="bg-amber-500/20 text-amber-400"
            href={`/workspaces/${id}/assets`}
          />
          <KpiCard
            label="Alto / Crítico Risco"
            value={stats != null ? (stats.high_risk + stats.critical_risk) : '—'}
            icon={ShieldAlert}
            color="bg-red-500/20 text-red-400"
            href={`/workspaces/${id}/assets`}
          />
        </div>

        {/* Two columns */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Recent files with detect button */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
              <h2 className="font-semibold text-white text-sm">Arquivos Recentes</h2>
              <Link href={`/workspaces/${id}/ingest`}
                className="flex items-center gap-1.5 text-brand-500 hover:text-brand-400 text-xs transition-colors">
                <Upload size={12} /> Adicionar
              </Link>
            </div>
            <div className="divide-y divide-slate-700/50">
              {files.length === 0 ? (
                <p className="text-slate-500 text-sm text-center py-8">Nenhum arquivo ainda</p>
              ) : files.slice(0, 5).map((f) => (
                <div key={f.id} className="px-5 py-3 flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-white text-sm truncate">{f.original_filename}</p>
                    <p className="text-slate-500 text-xs">{formatFileSize(f.file_size)}</p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${FILE_STATUS_STYLE[f.status] ?? FILE_STATUS_STYLE.uploaded}`}>
                    {FILE_STATUS_LABEL[f.status] ?? f.status}
                  </span>
                  {f.status === 'uploaded' && (
                    <button
                      onClick={() => handleDetect(f.id)}
                      disabled={detectingId === f.id}
                      title="Iniciar detecção"
                      className="text-brand-400 hover:text-brand-300 transition-colors disabled:opacity-50"
                    >
                      {detectingId === f.id
                        ? <Loader2 size={14} className="animate-spin" />
                        : <Play size={14} />
                      }
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Audit log */}
          <div className="bg-slate-800 border border-slate-700 rounded-xl">
            <div className="px-5 py-4 border-b border-slate-700">
              <h2 className="font-semibold text-white text-sm">Log de Auditoria</h2>
            </div>
            <div className="divide-y divide-slate-700/50">
              {logs.length === 0 ? (
                <p className="text-slate-500 text-sm text-center py-8">Nenhuma ação registrada</p>
              ) : logs.slice(0, 8).map((log) => (
                <div key={log.id} className="px-5 py-3">
                  <div className="flex items-center justify-between">
                    <code className="text-brand-500 text-xs">{log.action}</code>
                    <span className="text-slate-500 text-xs">
                      {formatDistanceToNow(new Date(log.created_at), { addSuffix: true, locale: ptBR })}
                    </span>
                  </div>
                  <p className="text-slate-400 text-xs mt-0.5 truncate">{log.user_email}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  )
}
