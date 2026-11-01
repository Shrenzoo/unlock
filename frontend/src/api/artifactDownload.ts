import { api } from './index'
/** Private artifacts never put session credentials in a URL or browser history. */
export async function downloadPrivateArtifact(id: string, filename = `unlock-${id}.zip`) {
  const r = await fetch(api.artifactUrl(id), { headers: api.artifactHeaders?.() })
  if (!r.ok) throw new Error('Artifact could not be downloaded. Re-enter your judge code if the session expired.')
  const url = URL.createObjectURL(await r.blob())
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}
