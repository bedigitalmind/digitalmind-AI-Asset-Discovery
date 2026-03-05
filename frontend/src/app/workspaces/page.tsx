'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { listWorkspaces, createWorkspace } from '@/lib/api'
import { isAuthenticated, getUser } from '@/lib/auth'
import AppShell from '@/components/layout/AppShell'
import type { Workspace } from '@/types'
import { Plus, Building2, Users, X } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { ptBR } from 'date-fns/locale'

export default function WorkspacesPage() {
  const router = useRouter()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', slug: '', description: '', industry: '', company_size: '', contact_email: '' })
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const user = getUser()

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    listWorkspaces().then(setWorkspaces).finally(() => setLoading(false))
  }, [router])

  const statusColor = (s: string) =>
    s === 'active' ? 'bg-emerald-500/20 text-emerald-400' :
    s === 'paused' ? 'bg-yellow-500/20 text-yellow-400' :
    'bg-slate-500/20 text-slate-400'

  const statusLabel = (s: string) =>
    s === 'active' ? 'Ativo' : s === 'paused' ? 'Pausado' : 'Arquivado'

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault(); setError(''); setCreating(true)
    try {
      const ws = await createWorkspace(form)
      setWorkspaces(prev => [ws, ...prev])
      setShowCreate(false)
      setForm({ name: '', slug: '', description: '', industry: '', company_size: '', contact_email: '' })
    } catch (err: unknown) {
      setError((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Erro ao criar workspace')
    } finally { setCreating(false) }
  }

  return (
    <AppShell>
      <div className="p-8 max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white">Clientes</h1>
            <p className="text-slate-400 mt-1 text-sm">
              {workspaces.length} workspace{workspaces.length !== 1 ? 's' : ''} disponíveis
            </p>
          </div>
          {user?.is_platform_admin && (
            <button onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 bg-brand-500 hover:bg-brand-600 text-white
                         px-4 py-2 rounded-lg text-sm font-medium transition-colors">
              <Plus size={16} /> Novo Cliente
            </button>
          )}
        </div>

        {/* Grid */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1,2,3].map(i => (
              <div key={i} className="bg-slate-800 border border-slate-700 rounded-xl p-6 animate-pulse h-40" />
            ))}
          </div>
        ) : workspaces.length === 0 ? (
          <div className="text-center py-20 text-slate-400">
            <Building2 size={40} className="mx-auto mb-3 opacity-50" />
            <p>Nenhum workspace encontrado</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {workspaces.map(ws => (
              <button key={ws.id} onClick={() => router.push(`/workspaces/${ws.id}`)}
                className="bg-slate-800 border border-slate-700 hover:border-brand-500/50
                           rounded-xl p-6 text-left transition-all hover:bg-slate-700/50 group">
                <div className="flex items-start justify-between mb-4">
                  <div className="w-10 h-10 rounded-lg bg-brand-500/20 flex items-center justify-center">
                    <Building2 size={18} className="text-brand-500" />
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColor(ws.status)}`}>
                    {statusLabel(ws.status)}
                  </span>
                </div>
                <h3 className="text-white font-semibold mb-1 group-hover:text-brand-500 transition-colors">
                  {ws.name}
                </h3>
                {ws.industry && <p className="text-slate-400 text-xs mb-3">{ws.industry}</p>}
                <p className="text-slate-500 text-xs">
                  Criado {formatDistanceToNow(new Date(ws.created_at), { addSuffix: true, locale: ptBR })}
                </p>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Create Modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-slate-700">
              <h2 className="text-lg font-semibold text-white">Novo Workspace</h2>
              <button onClick={() => setShowCreate(false)} className="text-slate-400 hover:text-white">
                <X size={20} />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              {[
                { label: 'Nome do cliente *', key: 'name', placeholder: 'Empresa XYZ', required: true },
                { label: 'Slug (identificador único) *', key: 'slug', placeholder: 'empresa-xyz', required: true },
                { label: 'Setor', key: 'industry', placeholder: 'Financeiro, Saúde, Varejo...' },
                { label: 'Porte', key: 'company_size', placeholder: '500-1000 funcionários' },
                { label: 'E-mail de contato', key: 'contact_email', placeholder: 'ti@empresa.com' },
              ].map(({ label, key, placeholder, required }) => (
                <div key={key}>
                  <label className="block text-sm text-slate-300 mb-1">{label}</label>
                  <input
                    required={required} value={form[key as keyof typeof form]}
                    onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))}
                    placeholder={placeholder}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2
                               text-white text-sm placeholder-slate-400 focus:outline-none
                               focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                  />
                </div>
              ))}
              {error && <p className="text-red-400 text-sm">{error}</p>}
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="flex-1 border border-slate-600 text-slate-300 hover:text-white
                             py-2 rounded-lg text-sm transition-colors">
                  Cancelar
                </button>
                <button type="submit" disabled={creating}
                  className="flex-1 bg-brand-500 hover:bg-brand-600 disabled:opacity-60
                             text-white py-2 rounded-lg text-sm font-medium transition-colors">
                  {creating ? 'Criando...' : 'Criar Workspace'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  )
}
