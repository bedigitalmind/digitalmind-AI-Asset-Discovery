'use client'
import { useEffect, useRef, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { getWorkspace, listFiles, uploadFile, deleteFile } from '@/lib/api'
import { isAuthenticated } from '@/lib/auth'
import AppShell from '@/components/layout/AppShell'
import type { Workspace, IngestionFile } from '@/types'
import { Upload, File, Trash2, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'
import { format } from 'date-fns'
import { ptBR } from 'date-fns/locale'

const ALLOWED_EXTENSIONS = ['csv', 'json', 'xml', 'txt', 'log', 'zip', 'gz', 'parquet', 'ndjson', 'jsonl']

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface UploadItem { file: File; status: 'pending' | 'uploading' | 'done' | 'error'; error?: string }

export default function IngestPage() {
  const router = useRouter()
  const params = useParams()
  const id = Number(params.id)
  const dropRef = useRef<HTMLDivElement>(null)

  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [files, setFiles] = useState<IngestionFile[]>([])
  const [queue, setQueue] = useState<UploadItem[]>([])
  const [dragging, setDragging] = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)

  useEffect(() => {
    if (!isAuthenticated()) { router.replace('/login'); return }
    getWorkspace(id).then(setWorkspace)
    loadFiles()
  }, [id, router])

  async function loadFiles() {
    const r = await listFiles(id).catch(() => ({ items: [] }))
    setFiles(r.items || [])
  }

  const handleFiles = useCallback((newFiles: FileList | null) => {
    if (!newFiles) return
    const items: UploadItem[] = []
    for (const f of Array.from(newFiles)) {
      const ext = f.name.split('.').pop()?.toLowerCase()
      if (!ext || !ALLOWED_EXTENSIONS.includes(ext)) continue
      items.push({ file: f, status: 'pending' })
    }
    setQueue(prev => [...prev, ...items])
  }, [])

  async function processQueue(items: UploadItem[]) {
    for (let i = 0; i < items.length; i++) {
      if (items[i].status !== 'pending') continue
      setQueue(prev => prev.map((q, idx) =>
        q.file === items[i].file ? { ...q, status: 'uploading' } : q
      ))
      try {
        await uploadFile(id, items[i].file)
        setQueue(prev => prev.map(q =>
          q.file === items[i].file ? { ...q, status: 'done' } : q
        ))
      } catch (err: unknown) {
        const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Erro no upload'
        setQueue(prev => prev.map(q =>
          q.file === items[i].file ? { ...q, status: 'error', error: msg } : q
        ))
      }
    }
    await loadFiles()
  }

  async function startUpload() {
    const pending = queue.filter(q => q.status === 'pending')
    if (pending.length === 0) return
    await processQueue(pending)
  }

  async function handleDelete(fileId: number) {
    setDeleting(fileId)
    try {
      await deleteFile(id, fileId)
      setFiles(prev => prev.filter(f => f.id !== fileId))
    } finally { setDeleting(null) }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const pendingCount = queue.filter(q => q.status === 'pending').length
  const doneCount = queue.filter(q => q.status === 'done').length

  return (
    <AppShell workspaceId={id} workspaceName={workspace?.name}>
      <div className="p-8 max-w-5xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white">Ingestão de Dados</h1>
          <p className="text-slate-400 mt-1 text-sm">
            Envie arquivos de log, exports de ferramentas e configurações para análise
          </p>
        </div>

        {/* Drop Zone */}
        <div
          ref={dropRef}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`border-2 border-dashed rounded-2xl p-10 text-center transition-all mb-6
            ${dragging
              ? 'border-brand-500 bg-brand-500/10'
              : 'border-slate-600 hover:border-slate-500'}`}
        >
          <Upload size={36} className="mx-auto mb-3 text-slate-400" />
          <p className="text-white font-medium mb-1">Arraste arquivos aqui ou clique para selecionar</p>
          <p className="text-slate-400 text-sm mb-4">
            Formatos: {ALLOWED_EXTENSIONS.join(', ')} · Máximo 500MB por arquivo
          </p>
          <label className="cursor-pointer bg-brand-500 hover:bg-brand-600 text-white
                            px-5 py-2 rounded-lg text-sm font-medium transition-colors inline-block">
            Selecionar Arquivos
            <input type="file" multiple className="hidden"
              accept={ALLOWED_EXTENSIONS.map(e => `.${e}`).join(',')}
              onChange={e => handleFiles(e.target.files)} />
          </label>
        </div>

        {/* Queue */}
        {queue.length > 0 && (
          <div className="bg-slate-800 border border-slate-700 rounded-xl mb-6">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700">
              <h2 className="font-semibold text-white text-sm">
                Fila de Upload ({doneCount}/{queue.length})
              </h2>
              {pendingCount > 0 && (
                <button onClick={startUpload}
                  className="bg-brand-500 hover:bg-brand-600 text-white px-4 py-1.5
                             rounded-lg text-xs font-medium transition-colors">
                  Enviar {pendingCount} arquivo{pendingCount !== 1 ? 's' : ''}
                </button>
              )}
            </div>
            <div className="divide-y divide-slate-700/50">
              {queue.map((item, i) => (
                <div key={i} className="px-5 py-3 flex items-center gap-3">
                  <File size={16} className="text-slate-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm truncate">{item.file.name}</p>
                    {item.error && <p className="text-red-400 text-xs">{item.error}</p>}
                  </div>
                  <span className="text-slate-400 text-xs">{formatFileSize(item.file.size)}</span>
                  {item.status === 'pending' && <span className="text-slate-400 text-xs">Pendente</span>}
                  {item.status === 'uploading' && <Loader2 size={14} className="text-brand-500 animate-spin" />}
                  {item.status === 'done' && <CheckCircle size={14} className="text-emerald-400" />}
                  {item.status === 'error' && <AlertCircle size={14} className="text-red-400" />}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Uploaded files */}
        <div className="bg-slate-800 border border-slate-700 rounded-xl">
          <div className="px-5 py-4 border-b border-slate-700">
            <h2 className="font-semibold text-white text-sm">Arquivos ({files.length})</h2>
          </div>
          {files.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-10">Nenhum arquivo ainda</p>
          ) : (
            <div className="divide-y divide-slate-700/50">
              {files.map(f => (
                <div key={f.id} className="px-5 py-3 flex items-center gap-3">
                  <File size={15} className="text-slate-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm truncate">{f.original_filename}</p>
                    <p className="text-slate-500 text-xs">
                      {formatFileSize(f.file_size)} · {f.uploaded_by_email} ·{' '}
                      {format(new Date(f.created_at), "dd MMM yyyy 'às' HH:mm", { locale: ptBR })}
                    </p>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400">
                    {f.status}
                  </span>
                  <button onClick={() => handleDelete(f.id)} disabled={deleting === f.id}
                    className="text-slate-500 hover:text-red-400 transition-colors ml-1">
                    {deleting === f.id
                      ? <Loader2 size={14} className="animate-spin" />
                      : <Trash2 size={14} />}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  )
}
