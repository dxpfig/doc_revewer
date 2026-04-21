import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api, LONG_API_TIMEOUT_MS, login, setToken, type UserInfo } from './api/client'

type Task = {
  task_id: string
  doc_name?: string
  standard_id?: string
  status: string
  current_stage: string
  overall_progress: number
  failed_rules: number
}

function App() {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (!token) {
      setLoading(false)
      return
    }
    setToken(token)
    api
      .get('/auth/me')
      .then((res) => setUser(res.data.data))
      .catch(() => {
        localStorage.removeItem('token')
        setToken(null)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="center-page">加载中...</div>

  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<LoginPage onLoggedIn={(u, token) => {
          localStorage.setItem('token', token)
          setToken(token)
          setUser(u)
          // 根据角色决定跳转页面
          navigate(u.role === 'admin' ? '/standards' : '/my-tasks')
        }} />} />
      </Routes>
    )
  }

  const menu = user.role === 'admin'
    ? [
        { to: '/standards', label: '标准管理' },
        { to: '/rules', label: '规则管理' },
        { to: '/model-providers', label: '模型配置' },
        { to: '/tasks', label: '全站任务' },
        { to: '/exports', label: '导出中心' },
      ]
    : [
        { to: '/review/new', label: '发起审查' },
        { to: '/my-tasks', label: '我的任务' },
        { to: '/exports', label: '导出中心' },
      ]

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div className="brand-block">
          <div className="brand-title">文档审查工具</div>
          <div className="brand-subtitle">Document Review Workspace</div>
        </div>
        <div className="top-right">
          {location.pathname.startsWith('/rules') ||
          location.pathname.startsWith('/my-tasks/') ||
          location.pathname.startsWith('/results/') ? (
            <button className="btn btn-ghost top-back-btn" onClick={() => navigate(-1)}>
              返回
            </button>
          ) : null}
          <span className="role-tag">{user.role === 'admin' ? '管理员' : '普通用户'}</span>
          <button
            className="btn btn-ghost"
            onClick={() => {
              localStorage.removeItem('token')
              setToken(null)
              setUser(null)
            }}
          >
            退出
          </button>
        </div>
      </header>
      <div className="body">
        <aside className="sider">
          {menu.map((m) => (
            <NavLink
              key={m.to}
              to={m.to}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              {m.label}
            </NavLink>
          ))}
        </aside>
        <main className="content">
          <Routes>
            <Route path="/" element={<Navigate to={user.role === 'admin' ? '/standards' : '/my-tasks'} replace />} />
            <Route path="/review/new" element={<ReviewCreatePage />} />
            <Route path="/my-tasks" element={<MyTasksPage />} />
            <Route path="/my-tasks/:id" element={<TaskDetailPage />} />
            <Route path="/results/:id" element={<ResultPage />} />
            <Route path="/standards" element={<StandardsPage />} />
            <Route path="/model-providers" element={<ModelProvidersPage />} />
            <Route path="/rules" element={user.role === 'admin' ? <RulesPage /> : <Navigate to="/" replace />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/exports" element={<ExportsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

function LoginPage({ onLoggedIn }: { onLoggedIn: (user: UserInfo, token: string) => void }) {
  const [role, setRole] = useState<'admin' | 'user'>('user')
  const [username, setUsername] = useState('user1')
  const [error, setError] = useState('')

  return (
    <div className="login-layout">
      <div className="login-left center-page">
        <div className="card auth-card">
          <h2>登录</h2>
          <label>用户名</label>
          <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} />
          <label>角色</label>
          <select className="input" value={role} onChange={(e) => setRole(e.target.value as 'admin' | 'user')}>
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
          <button
            className="btn btn-primary"
            onClick={async () => {
              try {
                const data = await login(username, role)
                onLoggedIn({ user_id: data.username, role: data.role }, data.token)
              } catch {
                setError('登录失败，请重试')
              }
            }}
          >
            登录
          </button>
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      </div>
      <div className="login-hero">
        <div className="login-hero-overlay">
          <h1>文档审查工具</h1>
          <p>文档智能审查平台</p>
        </div>
      </div>
    </div>
  )
}

function ReviewCreatePage() {
  const [standards, setStandards] = useState<any[]>([])
  const [standardInput, setStandardInput] = useState('')
  const [showStandardDropdown, setShowStandardDropdown] = useState(false)
  const [standardId, setStandardId] = useState('')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [reviewFileName, setReviewFileName] = useState('未选择文件')
  const [taskId, setTaskId] = useState('')
  const [error, setError] = useState('')
  const reviewFileInputRef = useRef<HTMLInputElement | null>(null)

  const loadStandards = async () => {
    try {
      const res = await api.get('/standards')
      const rows = res.data.data as any[]
      setStandards(rows)
      if (!standardId && rows.length > 0) {
        setStandardId(rows[0].id)
        setStandardInput(`${rows[0].name}（${rows[0].id}）`)
      }
    } catch {
      setStandards([])
    }
  }

  useEffect(() => {
    void loadStandards()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filteredStandards = standards.filter((s) => {
    const kw = standardInput.trim().toLowerCase()
    if (!kw) return true
    return s.name.toLowerCase().includes(kw) || s.id.toLowerCase().includes(kw)
  })

  const applyStandard = (s: any) => {
    setStandardId(s.id)
    setStandardInput(`${s.name}（${s.id}）`)
    setShowStandardDropdown(false)
    setError('')
  }

  const onPickFile = (file: File | null) => {
    setError('')
    if (!file) {
      setSelectedFile(null)
      setReviewFileName('未选择文件')
      return
    }
    const isDocx = file.name.toLowerCase().endsWith('.docx')
    if (!isDocx) {
      setSelectedFile(null)
      setReviewFileName('未选择文件')
      setError('文件仅支持 docx 格式')
      return
    }
    const maxBytes = 500 * 1024 * 1024
    if (file.size > maxBytes) {
      setSelectedFile(null)
      setReviewFileName('未选择文件')
      setError('文件大小不能超过 500MB')
      return
    }
    setSelectedFile(file)
    setReviewFileName(file.name)
  }

  const submit = async () => {
    setError('')
    if (!standardId) {
      const exact = standards.find(
        (s) => standardInput.includes(s.id) || standardInput.includes(s.name)
      )
      if (exact) {
        setStandardId(exact.id)
      } else {
        setError('请选择审查标准')
        return
      }
    }
    if (!standardId) {
      return
    }
    if (!selectedFile) {
      setError('请上传待审查文档')
      return
    }
    const form = new FormData()
    form.append('standard_id', standardId)
    form.append('file', selectedFile)
    try {
      const res = await api.post('/review-tasks', form)
      setTaskId(res.data.data.task_id)
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '提交失败')
    }
  }

  return (
    <section>
      <div className="section-head">
        <h2>发起审查</h2>
      </div>
      <div className="grid-two review-layout">
        <div className="card">
          <label>审查标准</label>
          <div className="combo-wrap">
            <input
              className="input"
              value={standardInput}
              onChange={(e) => {
                setStandardInput(e.target.value)
                setShowStandardDropdown(true)
                setStandardId('')
              }}
              onFocus={() => setShowStandardDropdown(true)}
              placeholder="输入关键字联想标准（名称或ID）"
              aria-label="审查标准搜索输入框"
            />
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() => setShowStandardDropdown((v) => !v)}
              title="展开全部已发布标准"
            >
              ▼
            </button>
          </div>
          {showStandardDropdown ? (
            <div className="combo-panel" role="listbox" aria-label="审查标准下拉列表">
              {filteredStandards.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={`combo-item${standardId === s.id ? ' active' : ''}`}
                  onClick={() => applyStandard(s)}
                  role="option"
                  aria-selected={standardId === s.id}
                >
                  <span className="combo-item-name">{s.name}</span>
                  <span className="combo-item-id">{s.id}</span>
                </button>
              ))}
            </div>
          ) : null}
          <label>待审查文档</label>
          <div className="upload-row">
            <input className="input upload-filename" value={reviewFileName} readOnly />
            <button className="btn btn-secondary" type="button" onClick={() => reviewFileInputRef.current?.click()}>
              选择文件
            </button>
          </div>
          <input
            ref={reviewFileInputRef}
            type="file"
            accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            style={{ display: 'none' }}
            onChange={(e) => {
              onPickFile(e.target.files?.[0] ?? null)
              e.currentTarget.value = ''
            }}
          />
          <p style={{ margin: 0, color: '#64748b', fontSize: 13 }}>
            文件仅支持 docx 格式，文件大小不超过 500MB
          </p>
          <button className="btn btn-primary" onClick={submit}>创建任务</button>
          {taskId ? <p>任务已创建：{taskId}</p> : null}
          {error ? <p className="error-text">{error}</p> : null}
        </div>
      </div>
    </section>
  )
}

function MyTasksPage() {
  const [items, setItems] = useState<Task[]>([])
  const [standardNameMap, setStandardNameMap] = useState<Record<string, string>>({})
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const [tasksRes, standardsRes] = await Promise.all([
        api.get('/review-tasks'),
        api.get('/standards').catch(() => ({ data: { data: [] } })),
      ])
      setItems(tasksRes.data.data)
      const map: Record<string, string> = {}
      ;((standardsRes.data?.data ?? []) as any[]).forEach((s) => {
        if (s?.id) map[s.id] = s.name ?? s.id
      })
      setStandardNameMap(map)
    } catch {
      setError('加载任务失败')
    }
  }

  const handleDelete = async (taskId: string) => {
    if (!window.confirm('确定删除该任务吗？该操作不可撤销。')) return
    try {
      await api.delete(`/review-tasks/${taskId}`)
      setItems(items.filter(t => t.task_id !== taskId))
    } catch {
      setError('删除失败')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  return (
    <section>
      <div className="section-head">
        <h2>我的任务</h2>
        <button className="btn btn-secondary" onClick={() => void load()}>刷新</button>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      <table className="table">
        <thead>
          <tr><th className="col-index">序号</th><th>用户上传文档名称</th><th>审查标准</th><th>状态</th><th>进度</th><th>失败数</th><th>操作</th></tr>
        </thead>
        <tbody>
          {items.map((t, index) => (
            <tr key={t.task_id}>
              <td className="col-index">{index + 1}</td>
              <td>{t.doc_name || '-'}</td>
              <td>{(t.standard_id && standardNameMap[t.standard_id]) || t.standard_id || '-'}</td>
              <td>{t.status}</td>
              <td>{t.overall_progress}%</td>
              <td>{t.failed_rules}</td>
              <td>
                <div className="row-actions">
                  <Link className="btn btn-secondary btn-sm" to={`/my-tasks/${t.task_id}`}>详情</Link>
                  <Link className="btn btn-primary btn-sm" to={`/results/${t.task_id}`}>结果</Link>
                  <button className="btn btn-danger btn-sm" onClick={() => handleDelete(t.task_id)}>删除</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function TaskDetailPage() {
  const taskId = useMemo(() => window.location.pathname.split('/').pop() ?? '', [])
  const [task, setTask] = useState<Task | null>(null)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const res = await api.get(`/review-tasks/${taskId}`)
      setTask(res.data.data)
      setError('')
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '加载失败')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  return (
    <section>
      <div className="section-head">
        <h2>任务详情</h2>
        <button className="btn btn-secondary" onClick={() => void load()}>刷新进度</button>
      </div>
      {task ? (
        <div className="stack">
          <div className="card">
            <p>任务ID：{task.task_id}</p>
            <p>状态：{task.status}</p>
            <p>阶段：{task.current_stage}</p>
            <p>进度：{task.overall_progress}%</p>
            <p>失败规则数：{task.failed_rules}</p>
          </div>
          {task.status === 'processing' && task.current_stage && (
            <div className="card">
              <h3>处理进度</h3>
              <p style={{ color: '#2563eb', fontWeight: 500 }}>{task.current_stage}</p>
              <div style={{ marginTop: 8 }}>
                <div style={{ width: '100%', height: 8, background: '#e5e7eb', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ width: `${task.overall_progress}%`, height: '100%', background: '#2563eb', transition: 'width 0.3s' }} />
                </div>
                <p style={{ marginTop: 4, fontSize: 13, color: '#6b7280' }}>{task.overall_progress}% 完成</p>
              </div>
            </div>
          )}
        </div>
      ) : null}
      {error ? <p className="error-text">{error}</p> : null}
    </section>
  )
}

function ResultPage() {
  const taskId = useMemo(() => window.location.pathname.split('/').pop() ?? '', [])
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const res = await api.get(`/review-tasks/${taskId}/result`)
      setResult(res.data.data)
      setError('')
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '任务尚未完成或执行失败')
    }
  }

  const exportPdf = async () => {
    try {
      const res = await api.post(`/review-tasks/${taskId}/exports/review-pdf`)
      const downloadUrl = res.data.data.download_url
      // Open PDF in new tab
      window.open(downloadUrl, '_blank')
    } catch (e: any) {
      alert(e?.response?.data?.detail?.message ?? '导出失败')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  return (
    <section>
      <div className="section-head">
        <h2>审查结果</h2>
      </div>
      <div className="inline-actions">
        <button className="btn btn-secondary" onClick={() => void load()}>刷新结果</button>
        <button className="btn btn-primary" onClick={() => void exportPdf()}>导出PDF</button>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      {result ? (
        <div className="stack">
          <div className="card">
            <h3>审查汇总</h3>
            <div className="grid-two" style={{ marginTop: 12 }}>
              <div>
                <p style={{ fontSize: 24, fontWeight: 600, color: result.passed_rules >= result.total_rules * 0.8 ? '#10b981' : '#ef4444' }}>
                  {result.passed_rules}/{result.total_rules}
                </p>
                <p style={{ color: '#6b7280', fontSize: 13 }}>通过规则</p>
              </div>
              <div>
                <p style={{ fontSize: 24, fontWeight: 600, color: '#ef4444' }}>
                  {result.failed_rules}
                </p>
                <p style={{ color: '#6b7280', fontSize: 13 }}>不符合规则</p>
              </div>
            </div>
            <p style={{ marginTop: 16, color: '#6b7280', fontSize: 13 }}>{result.ai_conclusion}</p>
            <p className="disclaimer">{result.disclaimer}</p>
          </div>

          <div className="card">
            <h3>不符合项详情 ({result.non_compliance_items?.length || 0} 项)</h3>
            {result.non_compliance_items?.length ? (
              <div className="stack" style={{ marginTop: 16 }}>
                {result.non_compliance_items.map((item: any, idx: number) => (
                  <div key={idx} style={{ padding: 16, background: '#fef2f2', borderRadius: 8, border: '1px solid #fecaca' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                      <span style={{ background: '#ef4444', color: 'white', padding: '2px 8px', borderRadius: 4, fontSize: 12, fontWeight: 500 }}>
                        规则 {item.rule_id}
                      </span>
                      <span style={{ fontWeight: 600, color: '#1f2937' }}>{item.rule_title}</span>
                    </div>
                    {item.matched_text && (
                      <div style={{ marginTop: 12 }}>
                        <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>文档匹配内容：</p>
                        <pre style={{ margin: 0, padding: 12, background: 'white', borderRadius: 4, fontSize: 13, whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 200, overflow: 'auto' }}>
{item.matched_text}
                        </pre>
                      </div>
                    )}
                    {item.evidence && (
                      <div style={{ marginTop: 12 }}>
                        <p style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>AI 证据：</p>
                        <p style={{ margin: 0, fontSize: 13, color: '#4b5563', fontStyle: 'italic' }}>{item.evidence}</p>
                      </div>
                    )}
                    {item.rule_group && (
                      <p style={{ marginTop: 8, fontSize: 12, color: '#9ca3af' }}>规则分组：{item.rule_group}</p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: '#10b981', marginTop: 12 }}>✓ 所有规则均已通过</p>
            )}
          </div>

          <div className="card">
            <h3>规则检测失败项</h3>
            {result.rule_failure_items?.length ? (
              <ul>
                {result.rule_failure_items.map((item: any, idx: number) => (
                  <li key={idx}>{item.rule_id} / {item.failure_code} / {item.failure_reason}</li>
                ))}
              </ul>
            ) : <p>无</p>}
          </div>
        </div>
      ) : null}
    </section>
  )
}

function StandardsPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<any[]>([])
  const [standardName, setStandardName] = useState('新导入标准')
  const [showImportDialog, setShowImportDialog] = useState(false)
  const [uploadFileName, setUploadFileName] = useState('未选择文件')
  const [selectedUploadFile, setSelectedUploadFile] = useState<File | null>(null)
  const [contentMode, setContentMode] = useState<'raw' | 'format_only' | 'summarize'>('format_only')
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const load = async () => {
    try {
      const res = await api.get('/admin/standards')
      setItems(res.data.data)
      setError('')
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '加载标准列表失败')
    }
  }

  const onUpload = async (file: File) => {
    setUploading(true)
    setMessage('')
    setError('')
    try {
      const form = new FormData()
      form.append('name', standardName || file.name.replace(/\.pdf$/i, ''))
      form.append('file', file)
      form.append('content_mode', contentMode)
      const uploadRes = await api.post('/admin/standards', form, { timeout: LONG_API_TIMEOUT_MS })
      const uploadedStandardId = uploadRes.data.data.standard.id as string
      setMessage('导入成功，正在进入规则列表页...')
      await load()
      setShowImportDialog(false)
      setSelectedUploadFile(null)
      setUploadFileName('未选择文件')
      navigate(`/rules?standard_id=${encodeURIComponent(uploadedStandardId)}`)
    } catch (e: any) {
      const aborted =
        e?.code === 'ECONNABORTED' ||
        String(e?.message ?? '').toLowerCase().includes('timeout')
      const serverMsg = e?.response?.data?.detail?.message
      setError(
        aborted
          ? '请求超时：当前为「LLM 仅整理格式」时会按条文多次调用模型，耗时可能较长。已放宽前端等待时间；若仍超时，请缩短 PDF 页数或在后端改用异步解析。'
          : serverMsg ?? '导入失败',
      )
    } finally {
      setUploading(false)
    }
  }

  const deleteStandard = async (standardId: string) => {
    if (!window.confirm(`确认删除标准 ${standardId} 吗？该标准下规则将一并删除。`)) return
    try {
      await api.delete(`/admin/standards/${standardId}`)
      setMessage(`标准 ${standardId} 已删除`)
      await load()
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '删除标准失败')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  return (
    <section>
      <div className="section-head">
        <h2>标准管理</h2>
        <button className="btn btn-primary" onClick={() => setShowImportDialog(true)}>
          导入标准
        </button>
      </div>
      {message ? <p style={{ margin: 0, color: '#166534' }}>{message}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
      <table className="table">
        <thead><tr><th className="col-index">序号</th><th>名称</th><th>状态</th><th>规则数</th><th>操作</th></tr></thead>
        <tbody>
          {items.map((s, index) => (
            <tr key={s.id}>
              <td className="col-index">{index + 1}</td>
              <td>{s.name}</td>
              <td>{s.status}</td>
              <td>
                <Link to={`/rules?standard_id=${encodeURIComponent(s.id)}`}>{s.rules_count}</Link>
              </td>
              <td>
                <button
                  className="btn btn-danger"
                  onClick={(e) => {
                    e.stopPropagation()
                    void deleteStandard(s.id)
                  }}
                >
                  删除
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {showImportDialog ? (
        <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-label="导入标准">
          <div className={`dialog-card ${uploading ? 'is-loading' : ''}`}>
            <h3 style={{ margin: 0 }}>导入标准（PDF）</h3>
            <p className="dialog-desc">仅支持 PDF 文件。导入成功后将跳转到对应规则列表页。</p>
            <label className="dialog-desc" htmlFor="import-content-mode" style={{ display: 'block', marginBottom: 8 }}>
              规则内容策略
            </label>
            <select
              id="import-content-mode"
              className="input"
              style={{ width: '100%', marginBottom: 12 }}
              value={contentMode}
              disabled={uploading}
              onChange={(e) => setContentMode(e.target.value as 'raw' | 'format_only' | 'summarize')}
            >
              <option value="raw">仅原文（不调用 LLM）</option>
              <option value="format_only">LLM 仅整理格式</option>
              <option value="summarize">LLM 归纳条款</option>
            </select>
            <div className="upload-row">
              <input className="input upload-filename" value={uploadFileName} readOnly />
              <button
                className="btn btn-secondary"
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
              >
                选择文件
              </button>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              style={{ display: 'none' }}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) {
                  setSelectedUploadFile(file)
                  setUploadFileName(file.name)
                  setStandardName(file.name.replace(/\.pdf$/i, ''))
                }
                e.currentTarget.value = ''
              }}
              disabled={uploading}
            />
            <div className="inline-actions">
              <button
                className="btn btn-ghost"
                disabled={uploading}
                onClick={() => {
                  setShowImportDialog(false)
                  setSelectedUploadFile(null)
                  setUploadFileName('未选择文件')
                  setError('')
                }}
              >
                取消
              </button>
              <button
                className="btn btn-primary"
                disabled={uploading || !selectedUploadFile}
                onClick={() => {
                  if (selectedUploadFile) {
                    void onUpload(selectedUploadFile)
                  }
                }}
              >
                {uploading ? '导入中...' : '确认导入'}
              </button>
            </div>
            {uploading ? (
              <div className="loading-overlay">
                <div className="loading-spinner" />
                <span>正在导入并解析标准，请稍候...</span>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}

function RulesPage() {
  const [searchParams] = useSearchParams()
  const standardId = searchParams.get('standard_id')
  const [items, setItems] = useState<any[]>([])
  const [savingRuleId, setSavingRuleId] = useState('')
  const [editingRule, setEditingRule] = useState<any | null>(null)
  const [editingDraft, setEditingDraft] = useState({
    title: '',
    content: '',
    source_excerpt: '',
    source_page: 0,
  })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [standardStatus, setStandardStatus] = useState('')
  const [standardName, setStandardName] = useState('')
  const tableRef = useRef<HTMLTableElement>(null)
  const [colWidths, setColWidths] = useState<number[]>([])

  // 表格列宽拖动
  const handleMouseDown = (e: React.MouseEvent, colIndex: number) => {
    e.preventDefault()
    const startX = e.clientX
    const startWidths = colWidths.length > 0 ? [...colWidths] : Array(6).fill(0).map((_, i) => {
      const th = tableRef.current?.querySelectorAll('th')[i]
      return th?.offsetWidth || 0
    })

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startX
      const newWidths = [...startWidths]
      newWidths[colIndex] = Math.max(50, startWidths[colIndex] + delta)
      setColWidths(newWidths)
    }

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }

  useEffect(() => {
    api
      .get('/admin/rules')
      .then((res) => {
        const rows = res.data.data as any[]
        setItems(standardId ? rows.filter((r) => r.standard_id === standardId) : rows)
      })
      .catch(() => setItems([]))
  }, [standardId])

  useEffect(() => {
    if (!standardId) return
    api
      .get('/admin/standards')
      .then((res) => {
        const st = (res.data.data as any[]).find((s) => s.id === standardId)
        setStandardStatus(st?.status ?? '')
        setStandardName(st?.name ?? '')
      })
      .catch(() => {
        setStandardStatus('')
        setStandardName('')
      })
  }, [standardId])

  const saveRule = async (ruleId: string, payload: { title: string; content: string; source_excerpt: string; source_page: number }) => {
    const rule = items.find((r) => r.id === ruleId)
    if (!rule) return false
    setSavingRuleId(ruleId)
    try {
      await api.patch(`/admin/rules/${ruleId}`, {
        title: payload.title,
        content: payload.content,
        source_page: Number(payload.source_page),
        source_excerpt: payload.source_excerpt,
        enabled: rule.enabled,
      })
      setItems((prev) =>
        prev.map((r) =>
          r.id === ruleId
            ? {
                ...r,
                title: payload.title,
                content: payload.content,
                source_excerpt: payload.source_excerpt,
                source_page: Number(payload.source_page),
              }
            : r
        )
      )
      setMessage(`规则 ${ruleId} 已保存`)
      setError('')
      return true
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '保存规则失败')
      return false
    } finally {
      setSavingRuleId('')
    }
  }

  const deleteRule = async (ruleId: string) => {
    if (!window.confirm(`确认删除规则 ${ruleId} 吗？`)) return
    try {
      await api.delete(`/admin/rules/${ruleId}`)
      setItems((prev) => prev.filter((r) => r.id !== ruleId))
      setMessage(`规则 ${ruleId} 已删除`)
      setError('')
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '删除规则失败')
    }
  }

  const toggleRuleEnabled = async (ruleId: string, enabled: boolean) => {
    try {
      await api.patch(`/admin/rules/${ruleId}`, { enabled })
      setItems((prev) => prev.map((r) => (r.id === ruleId ? { ...r, enabled } : r)))
      setMessage(`规则 ${ruleId} 已${enabled ? '启用' : '停用'}`)
      setError('')
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '更新启用状态失败')
    }
  }

  const openEditDialog = (rule: any) => {
    setEditingRule(rule)
    setEditingDraft({
      title: rule.title ?? '',
      content: rule.content ?? '',
      source_excerpt: rule.source_excerpt ?? '',
      source_page: Number(rule.source_page ?? 0),
    })
  }

  const saveDraft = async () => {
    if (!standardId) return
    try {
      await api.post(`/admin/standards/${standardId}/save-draft`)
      setStandardStatus('draft')
      setMessage('已保存为草稿')
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '保存草稿失败')
    }
  }

  const publish = async () => {
    if (!standardId) return
    try {
      await api.post(`/admin/standards/${standardId}/publish`)
      setStandardStatus('published')
      setMessage('发布成功')
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '发布失败')
    }
  }

  return (
    <section>
      <div className="rules-page-head card">
        <div className="rules-title-row">
          <h2>{standardName || '规则列表'}</h2>
        </div>
        <div className="rules-meta-row">
          <span className="meta-pill">{standardId ? `标准ID：${standardId}` : '标准ID：-'}</span>
          <span className="meta-pill">当前状态：{standardStatus || '-'}</span>
        </div>
      </div>
      <div className="rules-table-card card">
        <div className="rules-table-head">
          <h3>规则列表</h3>
          <p>共 {items.length} 条规则。可逐条修改标题、规则正文、原文摘录、页码与启用状态，保存后立即生效到当前标准草稿。</p>
        </div>
        <div className="table-toolbar">
          <div className="table-status">{standardId ? `当前状态：${standardStatus || '-'}` : ''}</div>
          <div className="table-actions">
            {standardId ? <button className="btn btn-secondary" onClick={() => void saveDraft()}>保存为草稿</button> : null}
            {standardId ? <button className="btn btn-primary" onClick={() => void publish()}>发布</button> : null}
          </div>
        </div>
        <div className="rules-table-wrap">
          <table className="table rules-table" ref={tableRef}>
            <thead>
              <tr>
                <th className="col-index" style={colWidths[0] ? { width: colWidths[0] } : {}}>序号</th>
                <th style={colWidths[1] ? { width: colWidths[1] } : {}} onMouseDown={(e) => handleMouseDown(e, 1)}>标题</th>
                <th style={colWidths[2] ? { width: colWidths[2] } : {}} onMouseDown={(e) => handleMouseDown(e, 2)}>规则正文</th>
                <th style={colWidths[3] ? { width: colWidths[3] } : {}} onMouseDown={(e) => handleMouseDown(e, 3)}>原文摘录</th>
                <th className="col-page" style={colWidths[4] ? { width: colWidths[4] } : {}}>页面</th>
                <th className="col-actions" style={colWidths[5] ? { width: colWidths[5] } : {}}>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r, index) => (
                <tr key={r.id}>
                  <td className="col-index">{index + 1}</td>
                  <td>
                    <div className="rule-cell-text" title={r.title}>{r.title}</div>
                  </td>
                  <td>
                    <div className="rule-cell-text" title={r.content}>{r.content}</div>
                  </td>
                  <td>
                    <div className="rule-cell-text" title={r.source_excerpt}>{r.source_excerpt}</div>
                  </td>
                  <td>
                    <span>{r.source_page}</span>
                  </td>
                  <td>
                    <div className="row-actions">
                      <button className="btn btn-secondary btn-sm" onClick={() => openEditDialog(r)}>
                        编辑
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => void toggleRuleEnabled(r.id, !r.enabled)}
                      >
                        {r.enabled ? '停用' : '启用'}
                      </button>
                      <button className="btn btn-danger btn-sm" onClick={() => void deleteRule(r.id)}>删除</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {message ? <p style={{ color: '#166534' }}>{message}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}
      {editingRule ? (
        <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-label="编辑规则">
          <div className={`dialog-card ${savingRuleId === editingRule.id ? 'is-loading' : ''}`}>
            <h3 style={{ margin: 0 }}>编辑规则</h3>
            <p className="dialog-desc">规则ID：{editingRule.id}</p>
            <div className="rule-edit-form">
              <label htmlFor="rule-title">标题</label>
              <input
                id="rule-title"
                className="input"
                value={editingDraft.title}
                onChange={(e) => setEditingDraft((prev) => ({ ...prev, title: e.target.value }))}
              />
              <label htmlFor="rule-content">规则正文</label>
              <textarea
                id="rule-content"
                className="input"
                rows={4}
                value={editingDraft.content}
                onChange={(e) => setEditingDraft((prev) => ({ ...prev, content: e.target.value }))}
              />
              <label htmlFor="rule-excerpt">原文摘录</label>
              <input
                id="rule-excerpt"
                className="input"
                value={editingDraft.source_excerpt}
                onChange={(e) => setEditingDraft((prev) => ({ ...prev, source_excerpt: e.target.value }))}
              />
              <label htmlFor="rule-page">页面</label>
              <input
                id="rule-page"
                className="input"
                value={String(editingDraft.source_page)}
                onChange={(e) => setEditingDraft((prev) => ({ ...prev, source_page: Number(e.target.value || 0) }))}
              />
            </div>
            <div className="inline-actions">
              <button className="btn btn-ghost" onClick={() => setEditingRule(null)} disabled={savingRuleId === editingRule.id}>
                取消
              </button>
              <button
                className="btn btn-primary"
                disabled={savingRuleId === editingRule.id}
                onClick={async () => {
                  const ok = await saveRule(editingRule.id, {
                    ...editingDraft,
                  })
                  if (ok) setEditingRule(null)
                }}
              >
                {savingRuleId === editingRule.id ? '保存中...' : '保存'}
              </button>
            </div>
            {savingRuleId === editingRule.id ? (
              <div className="loading-overlay">
                <div className="loading-spinner" />
                <span>正在保存规则，请稍候...</span>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}

function TasksPage() {
  const [items, setItems] = useState<any[]>([])
  useEffect(() => {
    api.get('/review-tasks').then((res) => setItems(res.data.data)).catch(() => setItems([]))
  }, [])
  return (
    <section>
      <h2>全站任务</h2>
      <table className="table">
        <thead><tr><th>任务ID</th><th>状态</th><th>进度</th><th>所有者</th></tr></thead>
        <tbody>{items.map((t) => <tr key={t.task_id}><td>{t.task_id}</td><td>{t.status}</td><td>{t.overall_progress}%</td><td>{t.owner_id}</td></tr>)}</tbody>
      </table>
    </section>
  )
}

function ModelProvidersPage() {
  const [items, setItems] = useState<any[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [activeTab, setActiveTab] = useState<'llm' | 'embedding'>('llm')
  const [editingLlmId, setEditingLlmId] = useState<string | null>(null)
  const [editingEmbId, setEditingEmbId] = useState<string | null>(null)
  const [testingProviderId, setTestingProviderId] = useState<string | null>(null)

  // LLM provider form
  const [llmForm, setLlmForm] = useState({
    name: '',
    provider_type: 'openai_compatible',
    base_url: 'https://api.openai.com/v1',
    api_key: '',
    llm_model: '',
  })
  const [discoveringLlm, setDiscoveringLlm] = useState(false)
  const [discoveredLlmModels, setDiscoveredLlmModels] = useState<string[]>([])

  // Embedding provider form
  const [embForm, setEmbForm] = useState({
    name: '',
    provider_type: 'openai_compatible',
    base_url: 'https://api.openai.com/v1',
    api_key: '',
    embedding_model: '',
  })
  const [discoveringEmb, setDiscoveringEmb] = useState(false)
  const [discoveredEmbModels, setDiscoveredEmbModels] = useState<string[]>([])

  const load = async () => {
    try {
      const res = await api.get('/admin/model-providers')
      setItems(res.data.data)
      setError('')
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '加载模型配置失败')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const discoverLlmModels = async () => {
    if (!llmForm.base_url.trim()) { setError('请先填写 Base URL'); return }
    if (!llmForm.api_key.trim()) { setError('请先填写 API Key'); return }
    setDiscoveringLlm(true)
    setError('')
    setMessage('')
    try {
      const res = await api.post('/admin/model-providers/discover-llm-models', {
        provider_type: llmForm.provider_type,
        base_url: llmForm.base_url,
        api_key: llmForm.api_key,
      })
      const models = (res.data?.data?.models ?? []) as string[]
      setDiscoveredLlmModels(models)
      if (models.length > 0) {
        setLlmForm((p) => ({ ...p, llm_model: models[0] }))
        setMessage(`已发现 ${models.length} 个可用 LLM 模型`)
      } else {
        setError(res.data?.data?.reason ? `探测失败：${res.data.data.reason}` : '未发现可用模型')
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '读取模型列表失败')
    } finally {
      setDiscoveringLlm(false)
    }
  }

  const discoverEmbModels = async () => {
    if (!embForm.base_url.trim()) { setError('请先填写 Base URL'); return }
    if (!embForm.api_key.trim()) { setError('请先填写 API Key'); return }
    setDiscoveringEmb(true)
    setError('')
    setMessage('')
    try {
      const res = await api.post('/admin/model-providers/discover-llm-models', {
        provider_type: embForm.provider_type,
        base_url: embForm.base_url,
        api_key: embForm.api_key,
      })
      const models = (res.data?.data?.models ?? []) as string[]
      setDiscoveredEmbModels(models)
      if (models.length > 0) {
        setEmbForm((p) => ({ ...p, embedding_model: models[0] }))
        setMessage(`已发现 ${models.length} 个可用 Embedding 模型`)
      } else {
        setError(res.data?.data?.reason ? `探测失败：${res.data.data.reason}` : '未发现可用模型')
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '读取模型列表失败')
    } finally {
      setDiscoveringEmb(false)
    }
  }

  const submitLlm = async () => {
    if (!llmForm.name.trim()) { setError('请填写名称'); return }
    if (!llmForm.llm_model.trim()) { setError('请填写 LLM 模型'); return }
    try {
      if (editingLlmId) {
        const payload: Record<string, any> = {
          name: llmForm.name,
          provider_type: llmForm.provider_type,
          base_url: llmForm.base_url,
          llm_model: llmForm.llm_model,
          purpose: 'llm',
        }
        if (llmForm.api_key.trim()) payload.api_key = llmForm.api_key.trim()
        await api.patch(`/admin/model-providers/${editingLlmId}`, payload)
        setMessage('LLM 配置已更新')
      } else {
        if (!llmForm.api_key.trim()) { setError('请填写 API Key'); return }
        await api.post('/admin/model-providers', {
          ...llmForm,
          purpose: 'llm',
          embedding_model: '',  // LLM provider 不填 embedding
        })
        setMessage('LLM 配置已创建')
      }
      setLlmForm((p) => ({ ...p, api_key: '' }))
      setError('')
      setEditingLlmId(null)
      await load()
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? (editingLlmId ? '更新 LLM 配置失败' : '创建 LLM 配置失败'))
    }
  }

  const submitEmb = async () => {
    if (!embForm.name.trim()) { setError('请填写名称'); return }
    if (!embForm.embedding_model.trim()) { setError('请填写 Embedding 模型'); return }
    try {
      if (editingEmbId) {
        const payload: Record<string, any> = {
          name: embForm.name,
          provider_type: embForm.provider_type,
          base_url: embForm.base_url,
          embedding_model: embForm.embedding_model,
          purpose: 'embedding',
        }
        if (embForm.api_key.trim()) payload.api_key = embForm.api_key.trim()
        await api.patch(`/admin/model-providers/${editingEmbId}`, payload)
        setMessage('Embedding 配置已更新')
      } else {
        if (!embForm.api_key.trim()) { setError('请填写 API Key'); return }
        await api.post('/admin/model-providers', {
          ...embForm,
          purpose: 'embedding',
          llm_model: '',  // Embedding provider 不填 LLM
        })
        setMessage('Embedding 配置已创建')
      }
      setEmbForm((p) => ({ ...p, api_key: '' }))
      setError('')
      setEditingEmbId(null)
      await load()
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? (editingEmbId ? '更新 Embedding 配置失败' : '创建 Embedding 配置失败'))
    }
  }

  const markDefault = async (id: string) => {
    try {
      await api.patch(`/admin/model-providers/${id}`, { is_default: true, enabled: true })
      setMessage('默认模型已更新')
      setError('')
      await load()
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '更新默认配置失败')
    }
  }

  const toggleEnabled = async (item: any) => {
    try {
      await api.patch(`/admin/model-providers/${item.id}`, { enabled: !item.enabled })
      setMessage(`配置 ${item.name} 已${item.enabled ? '停用' : '启用'}`)
      setError('')
      await load()
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '更新启停失败')
    }
  }

  const testProvider = async (id: string) => {
    setTestingProviderId(id)
    setMessage('')
    setError('')
    try {
      const res = await api.post(`/admin/model-providers/${id}/test`)
      const info = res.data.data
      if (info.status === 'ok') {
        setMessage(`测试成功${info.latency_ms ? `，耗时 ${info.latency_ms}ms` : ''}${info.note ? `（${info.note}）` : ''}`)
      } else {
        setError(`测试失败${info.reason ? `：${info.reason}` : ''}`)
      }
    } catch (e: any) {
      setError(`测试异常：${e?.response?.data?.detail?.message ?? '连接测试失败'}`)
    } finally {
      setTestingProviderId(null)
    }
  }

  const selectProvider = (item: any) => {
    setError('')
    setMessage(`已加载配置：${item.name}`)
    if (activeTab === 'llm') {
      setEditingLlmId(item.id)
      setLlmForm({
        name: item.name ?? '',
        provider_type: item.provider_type ?? 'openai_compatible',
        base_url: item.base_url ?? '',
        api_key: '',
        llm_model: item.llm_model ?? '',
      })
    } else {
      setEditingEmbId(item.id)
      setEmbForm({
        name: item.name ?? '',
        provider_type: item.provider_type ?? 'openai_compatible',
        base_url: item.base_url ?? '',
        api_key: '',
        embedding_model: item.embedding_model ?? '',
      })
    }
  }

  const removeProvider = async (item: any) => {
    const okDelete = window.confirm(`确定删除配置「${item.name}」吗？该操作不可撤销。`)
    if (!okDelete) return
    try {
      await api.delete(`/admin/model-providers/${item.id}`)
      setMessage(`配置 ${item.name} 已删除`)
      setError('')
      if (editingLlmId === item.id) setEditingLlmId(null)
      if (editingEmbId === item.id) setEditingEmbId(null)
      await load()
    } catch (e: any) {
      setError(e?.response?.data?.detail?.message ?? '删除配置失败')
    }
  }

  const tabItems = activeTab === 'llm'
    ? items.filter((i) => i.purpose === 'llm' || i.purpose === 'both')
    : items.filter((i) => i.purpose === 'embedding' || i.purpose === 'both')

  return (
    <section>
      <div className="section-head">
        <h2>模型配置</h2>
        <button className="btn btn-secondary" onClick={() => void load()}>刷新</button>
      </div>

      {/* Tab switcher */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button
          className={`btn ${activeTab === 'llm' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => { setActiveTab('llm'); setError(''); setMessage('') }}
        >
          LLM 配置
        </button>
        <button
          className={`btn ${activeTab === 'embedding' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => { setActiveTab('embedding'); setError(''); setMessage('') }}
        >
          Embedding 向量配置
        </button>
      </div>

      {/* LLM Form */}
      {activeTab === 'llm' && (
        <div className="card" style={{ marginBottom: 12 }}>
          <h3 style={{ marginTop: 0 }}>{editingLlmId ? '编辑 LLM Provider' : '新增 LLM Provider'}</h3>
          <div className="grid-two">
            <div>
              <label>名称</label>
              <input className="input" placeholder="例如：DeepSeek API" value={llmForm.name} onChange={(e) => setLlmForm((p) => ({ ...p, name: e.target.value }))} />
            </div>
            <div>
              <label>Provider 类型</label>
              <select className="input" value={llmForm.provider_type} onChange={(e) => setLlmForm((p) => ({ ...p, provider_type: e.target.value }))}>
                <option value="openai_compatible">openai_compatible</option>
                <option value="anthropic">anthropic</option>
                <option value="minimax">minimax</option>
                <option value="deepseek">deepseek</option>
                <option value="ollama">ollama</option>
              </select>
            </div>
            <div>
              <label>Base URL</label>
              <input className="input" placeholder="https://api.deepseek.com/v1" value={llmForm.base_url} onChange={(e) => setLlmForm((p) => ({ ...p, base_url: e.target.value }))} />
            </div>
            <div>
              <label>API Key</label>
              <input className="input" value={llmForm.api_key} onChange={(e) => setLlmForm((p) => ({ ...p, api_key: e.target.value }))} type="password" />
            </div>
            <div>
              <label>LLM 模型</label>
              {discoveredLlmModels.length > 0 ? (
                <select className="input" value={llmForm.llm_model} onChange={(e) => setLlmForm((p) => ({ ...p, llm_model: e.target.value }))}>
                  {discoveredLlmModels.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              ) : (
                <input className="input" placeholder="例如：deepseek-chat" value={llmForm.llm_model} onChange={(e) => setLlmForm((p) => ({ ...p, llm_model: e.target.value }))} />
              )}
              <div className="inline-actions" style={{ marginTop: 8 }}>
                <button className="btn btn-secondary" type="button" onClick={() => void discoverLlmModels()} disabled={discoveringLlm}>
                  {discoveringLlm ? '读取中...' : '读取可用 LLM 模型'}
                </button>
              </div>
            </div>
          </div>
          <div className="inline-actions" style={{ marginTop: 12 }}>
            <button className="btn btn-primary" onClick={() => void submitLlm()}>{editingLlmId ? '更新 LLM 配置' : '保存 LLM 配置'}</button>
            {editingLlmId ? (
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setEditingLlmId(null)
                  setLlmForm({ name: '', provider_type: 'openai_compatible', base_url: 'https://api.openai.com/v1', api_key: '', llm_model: '' })
                  setMessage('已退出编辑模式')
                }}
              >
                取消编辑
              </button>
            ) : null}
          </div>
          {editingLlmId ? <p style={{ marginTop: 8, color: '#64748b', fontSize: 12 }}>提示：不修改 API Key 可留空；仅在你输入新 Key 时更新。</p> : null}
        </div>
      )}

      {/* Embedding Form */}
      {activeTab === 'embedding' && (
        <div className="card" style={{ marginBottom: 12 }}>
          <h3 style={{ marginTop: 0 }}>{editingEmbId ? '编辑 Embedding Provider' : '新增 Embedding Provider'}</h3>
          <div className="grid-two">
            <div>
              <label>名称</label>
              <input className="input" placeholder="例如：OpenAI Embedding" value={embForm.name} onChange={(e) => setEmbForm((p) => ({ ...p, name: e.target.value }))} />
            </div>
            <div>
              <label>Provider 类型</label>
              <select className="input" value={embForm.provider_type} onChange={(e) => setEmbForm((p) => ({ ...p, provider_type: e.target.value }))}>
                <option value="openai_compatible">openai_compatible</option>
                <option value="ollama">ollama</option>
              </select>
            </div>
            <div>
              <label>Base URL</label>
              <input className="input" placeholder="https://api.openai.com/v1" value={embForm.base_url} onChange={(e) => setEmbForm((p) => ({ ...p, base_url: e.target.value }))} />
            </div>
            <div>
              <label>API Key</label>
              <input className="input" value={embForm.api_key} onChange={(e) => setEmbForm((p) => ({ ...p, api_key: e.target.value }))} type="password" />
            </div>
            <div>
              <label>Embedding 模型</label>
              {discoveredEmbModels.length > 0 ? (
                <select className="input" value={embForm.embedding_model} onChange={(e) => setEmbForm((p) => ({ ...p, embedding_model: e.target.value }))}>
                  {discoveredEmbModels.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              ) : (
                <input className="input" placeholder="例如：text-embedding-3-small" value={embForm.embedding_model} onChange={(e) => setEmbForm((p) => ({ ...p, embedding_model: e.target.value }))} />
              )}
              <div className="inline-actions" style={{ marginTop: 8 }}>
                <button className="btn btn-secondary" type="button" onClick={() => void discoverEmbModels()} disabled={discoveringEmb}>
                  {discoveringEmb ? '读取中...' : '读取可用 Embedding 模型'}
                </button>
              </div>
            </div>
          </div>
          <div className="inline-actions" style={{ marginTop: 12 }}>
            <button className="btn btn-primary" onClick={() => void submitEmb()}>{editingEmbId ? '更新 Embedding 配置' : '保存 Embedding 配置'}</button>
            {editingEmbId ? (
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setEditingEmbId(null)
                  setEmbForm({ name: '', provider_type: 'openai_compatible', base_url: 'https://api.openai.com/v1', api_key: '', embedding_model: '' })
                  setMessage('已退出编辑模式')
                }}
              >
                取消编辑
              </button>
            ) : null}
          </div>
          {editingEmbId ? <p style={{ marginTop: 8, color: '#64748b', fontSize: 12 }}>提示：不修改 API Key 可留空；仅在你输入新 Key 时更新。</p> : null}
        </div>
      )}

      {message ? <p style={{ color: '#166534' }}>{message}</p> : null}
      {error ? <p className="error-text">{error}</p> : null}

      <table className="table">
        <thead>
          <tr>
            <th>名称</th>
            <th>用途</th>
            <th>类型</th>
            <th>Base URL</th>
            <th>模型</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {tabItems.map((item) => (
            <tr key={item.id} onClick={() => selectProvider(item)} style={{ cursor: 'pointer' }}>
              <td>{item.name}{item.is_default ? '（默认）' : ''}</td>
              <td>{item.purpose === 'llm' ? 'LLM' : item.purpose === 'embedding' ? 'Embedding' : 'Both'}</td>
              <td>{item.provider_type}</td>
              <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.base_url}</td>
              <td>{item.llm_model || '-'}{item.llm_model && item.embedding_model ? ' / ' : ''}{item.embedding_model || '-'}</td>
              <td>{item.enabled ? 'enabled' : 'disabled'}</td>
              <td>
                <div className="row-actions">
                  <button
                    className="btn btn-secondary btn-sm"
                    disabled={testingProviderId === item.id}
                    onClick={(e) => { e.stopPropagation(); void testProvider(item.id) }}
                  >
                    {testingProviderId === item.id ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                        <span className="loading-spinner" style={{ width: 12, height: 12 }} />
                        测试中...
                      </span>
                    ) : '测试'}
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); void toggleEnabled(item) }}>{item.enabled ? '停用' : '启用'}</button>
                  <button className="btn btn-primary btn-sm" onClick={(e) => { e.stopPropagation(); void markDefault(item.id) }}>设为默认</button>
                  <button className="btn btn-ghost btn-sm" onClick={(e) => { e.stopPropagation(); void removeProvider(item) }}>删除</button>
                </div>
              </td>
            </tr>
          ))}
          {tabItems.length === 0 ? (
            <tr>
              <td colSpan={7} style={{ color: '#64748b' }}>
                当前分类暂无配置，请填写上方表单后点击保存。
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </section>
  )
}

function ExportsPage() {
  return (
    <section>
      <h2>导出中心</h2>
      <p>当前为MVP版本，导出由结果页触发并返回下载地址。</p>
    </section>
  )
}

export default App
