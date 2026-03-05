'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { getWorkspace, listMembers, addMember } from '@/lib/api'
import { isAuthenticated, getUser } from '@/lib/auth'
import AppShell from '@/components/layout/AppShell'
import type { Workspace, WorkspaceMember } from '@/types'
import { UserPlus, X } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { ptBR } from 'date-fns/locale'

const ROLE_LABELS = { viewer: 'Viewer', analyst: 'Analyst', admin: 'Admin' }
const ROLE_COLORS = {
  viewer: 'bg-slate-500/20 text-slate-400',
  analyst: 'bg-brand-500/20 text-brand-400',
  admin: 'bg-purple-500/20 text-purple-400',
}

export default function UsersPage() {
  const router = useRouter()
  const params = useParams()
  const id = Number(params.id)
  const currentUser = getUser()

  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [members, setMembers] = useState<WorkspaceMember[]>([])
  const [showInvite, setShowInvite] = useState(false)
  const [form, setForm] = useState({ email: '', full_name: '', role: 'analyst', password: '' })
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    getWorkspace(id).then(setWorkspace)
    listMembers(id).then(setMembers)
  }, [id, router])

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault(); setError(''); setAdding(true)
    try {
      const m = await addMember(id, form)
      setMembers(prev => [m, ...prev])
      setShowInvite(false)
      setForm({ email: '', full_name: '', role: 'analyst', password: '' })
    } catch (err: unknown) {
      setError((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Erro ao adicionar membro')
    } finally { setAdding(false) }
  }

  return (
    <AppShell workspaceId={id} workspaceName={workspace?.name}>
      <div className="p-8 max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white">Membros</h1>
            <p className="text-slate-400 mt-1 text-sm">{members.length} membro{members.length !== 1 ? 's' : ''}</p>
          </div>
          <button onClick={() => setShowInvite(true)}
            className="flex items-center gap-2 bg-brand-500 hover:bg-brand-600 text-white
                       px-4 py-2 rounded-lg text-sm font-medium transition-colors">
            <UserPlus size={16} /> Adicionar Membro
          </button>
        </div>

        {/* Members table */}
        <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-700 text-left">
                <th className="px-5 py-3 text-slate-400 text-xs font-medium uppercase tracking-wide">Usuário</th>
                <th className="px-5 py-3 text-slate-400 text-xs font-medium uppercase tracking-wide">Papel</th>
                <th className="px-5 py-3 text-slate-400 text-xs font-medium uppercase tracking-wide">Adicionado</th>
                <th className="px-5 py-3 text-slate-400 text-xs font-medium uppercase tracking-wide">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {members.map(m => (
                <tr key={m.id} className="hover:bg-slate-700/30 transition-colors">
                  <td className="px-5 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-7 h-7 rounded-full bg-brand-500/30 flex items-center justify-center flex-shrink-0">
                        <span className="text-brand-400 text-xs font-medium">
                          {m.user.full_name.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <div>
                        <p className="text-white text-sm">{m.user.full_name}</p>
                        <p className="text-slate-400 text-xs">{m.user.email}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${ROLE_COLORS[m.role]}`}>
                      {ROLE_LABELS[m.role]}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-slate-400 text-xs">
                    {formatDistanceToNow(new Date(m.created_at), { addSuffix: true, locale: ptBR })}
                  </td>
                  <td className="px-5 py-3">
                    <span className={`text-xs px-2 py-1 rounded-full ${m.is_active ? 'bg-emerald-500/20 text-emerald-400' : 'bg-slate-500/20 text-slate-400'}`}>
                      {m.is_active ? 'Ativo' : 'Inativo'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {members.length === 0 && (
            <p className="text-slate-500 text-sm text-center py-10">Nenhum membro ainda</p>
          )}
        </div>
      </div>

      {/* Invite Modal */}
      {showInvite && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 border border-slate-700 rounded-2xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-slate-700">
              <h2 className="text-lg font-semibold text-white">Adicionar Membro</h2>
              <button onClick={() => setShowInvite(false)} className="text-slate-400 hover:text-white"><X size={20} /></button>
            </div>
            <form onSubmit={handleInvite} className="p-6 space-y-4">
              {[
                { label: 'Nome completo *', key: 'full_name', placeholder: 'João Silva', required: true },
                { label: 'E-mail *', key: 'email', placeholder: 'joao@empresa.com', required: true },
                { label: 'Senha inicial *', key: 'password', placeholder: '••••••••', required: true, type: 'password' },
              ].map(({ label, key, placeholder, required, type }) => (
                <div key={key}>
                  <label className="block text-sm text-slate-300 mb-1">{label}</label>
                  <input
                    required={required} type={type || 'text'}
                    value={form[key as keyof typeof form]}
                    onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))}
                    placeholder={placeholder}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2
                               text-white text-sm placeholder-slate-400 focus:outline-none
                               focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                  />
                </div>
              ))}
              <div>
                <label className="block text-sm text-slate-300 mb-1">Papel</label>
                <select value={form.role} onChange={e => setForm(p => ({ ...p, role: e.target.value }))}
                  className="w-full bg-slate-700 border border-slate-600 rounded-lg px-3 py-2
                             text-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-500">
                  <option value="viewer">Viewer — apenas visualizar</option>
                  <option value="analyst">Analyst — visualizar e editar análises</option>
                  <option value="admin">Admin — acesso total ao workspace</option>
                </select>
              </div>
              {error && <p className="text-red-400 text-sm">{error}</p>}
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowInvite(false)}
                  className="flex-1 border border-slate-600 text-slate-300 hover:text-white
                             py-2 rounded-lg text-sm transition-colors">Cancelar</button>
                <button type="submit" disabled={adding}
                  className="flex-1 bg-brand-500 hover:bg-brand-600 disabled:opacity-60
                             text-white py-2 rounded-lg text-sm font-medium transition-colors">
                  {adding ? 'Adicionando...' : 'Adicionar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  )
}
