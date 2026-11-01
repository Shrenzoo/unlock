import { useEffect, useRef, useState, type FormEvent } from 'react'
import { navigate } from '@/router'
import { validatePackage } from '@/api/client'
import { judgeCall, judgeOrigin, judgeToken, saveJudgeToken, clearJudgeToken } from '@/api/judgeSession'

type Session = { remaining: number; jobs: { id: string; state: string }[] }
type Job = { job_id: string; state: string; phase?: string; error?: string; project_id?: string; run_id?: string }

export function JudgeAccess() {
  const [session, setSession] = useState<Session | null>(null)
  const [code, setCode] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [target, setTarget] = useState('target')
  const [job, setJob] = useState<Job | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    if (judgeToken()) void judgeCall<Session>('/session').then(setSession).catch(() => clearJudgeToken())
    return () => { mounted.current = false }
  }, [])
  useEffect(() => {
    if (!job || !['queued', 'running'].includes(job.state)) return
    let cancelled = false
    const timer = setInterval(() => {
      void judgeCall<Job>(`/jobs/${job.job_id}`).then(next => { if (!cancelled) setJob(next) }).catch(e => { if (!cancelled) { setMessage(e.message); if (!judgeToken()) { setSession(null); setJob(null) } } })
    }, 2500)
    return () => { cancelled = true; clearInterval(timer) }
  }, [job?.job_id, job?.state])
  useEffect(() => {
    if (job && ['completed','failed','interrupted'].includes(job.state)) void judgeCall<Session>('/session').then(setSession).catch(() => {})
  }, [job?.state])
  async function login(e: FormEvent) {
    e.preventDefault(); setBusy(true); setMessage('')
    try {
      const result = await judgeCall<{ token: string }>('/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) })
      saveJudgeToken(result.token); setCode(''); setSession(await judgeCall<Session>('/session'))
    } catch (e) { setMessage((e as Error).message) }
    finally { if (mounted.current) setBusy(false) }
  }
  async function submit(e: FormEvent) {
    e.preventDefault(); setMessage('')
    const errors = validatePackage(files)
    if (errors.length) { setMessage(errors.map(x => x.message).join(' ')); return }
    if (files.reduce((n,f) => n+f.size,0) > 10*1024*1024) { setMessage('The judge upload limit is 10 MiB.'); return }
    setBusy(true)
    try {
      const body = new FormData(); files.forEach(f => body.append('package',f,f.name)); body.append('target_id',target)
      const result = await judgeCall<{ job_id: string }>('/jobs', { method: 'POST', body, headers: { 'Idempotency-Key': crypto.randomUUID() } })
      setJob({ job_id: result.job_id, state: 'queued' }); setSession(await judgeCall<Session>('/session'))
    } catch (e) { setMessage((e as Error).message) }
    finally { if (mounted.current) { setBusy(false); void judgeCall<Session>('/session').then(setSession).catch(() => {}) } }
  }
  function open(result: Job) {
    if (result.project_id && result.run_id) navigate(`/projects/${encodeURIComponent(result.project_id)}?judge=${result.job_id}&run=${encodeURIComponent(result.run_id)}`)
  }
  if (!judgeOrigin) return <p>The B02 demonstration is public. Judge uploads will be available when the judge service is connected.</p>
  return <section className="judge-access" aria-label="Judge access">
    <h2>Judge access</h2>
    {!session && <p>Explore the public B02 demo, or enter your judge code to upload an assembly and run fresh analysis.</p>}
    {!session ? <form onSubmit={login}>
      <label>Judge access code<input type="password" autoComplete="off" required value={code} onChange={e => setCode(e.target.value)} /></label>
      <button className="btn btn--primary" disabled={busy}>Unlock judge access</button>
    </form> : <>
      <p>Judge access unlocked · {session.remaining} analyses remaining in this session.</p>
      <p>Results are private to this tab. Sessions last two hours; download your results before ending the session.</p>
      <form onSubmit={submit}>
        <label>Assembly package<input type="file" multiple accept=".zip,.step,.stp,.json" disabled={busy || session.remaining===0 || !!job && ['queued','running'].includes(job.state)} onChange={e => setFiles(Array.from(e.target.files ?? []))} required /></label>
        <label>Repair target occurrence ID<input value={target} maxLength={128} pattern="[A-Za-z0-9_.-]+" required onChange={e => setTarget(e.target.value)} /></label>
        <p>One ZIP, or STEP plus manifest.json. Maximum 10 MiB. Six attempts are shared across judges, with up to two per session. One job runs at a time; attempts count even when analysis fails.</p>
        <p>Fresh CAD checks use the offline scripted decision policy. Live AI calls are disabled.</p>
        <button className="btn btn--primary" disabled={busy || session.remaining===0 || !!job && ['queued','running'].includes(job.state)}>Upload and analyze</button>
      </form>
      {job && <div role="status"><p>Analysis: {job.state}{job.phase ? ` · ${job.phase}` : ''}</p>{job.error && <p>No passing result is claimed: {job.error}</p>}{job.state==='completed' && <button className="btn btn--primary" onClick={() => open(job)}>Open verified result</button>}</div>}
      {session.jobs.length>0 && <ul>{session.jobs.map(j => <li key={j.id}><button className="btn btn--quiet btn--sm" onClick={() => { void judgeCall<Job>(`/jobs/${j.id}`).then(r => { setJob(r); if(r.state==='completed') open(r) }).catch(e => setMessage(e.message)) }}>View analysis · {j.state}</button></li>)}</ul>}
      <button className="btn btn--quiet btn--sm" onClick={() => { void judgeCall('/session',{method:'DELETE'}).catch(()=>{}); clearJudgeToken(); setSession(null); setJob(null) }}>End judge session</button>
    </>}
    {message && <p role="alert">{message}</p>}
  </section>
}
