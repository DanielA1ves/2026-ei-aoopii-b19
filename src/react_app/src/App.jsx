import { useState } from 'react'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'
const MIN_DURATION = 4
const MAX_DURATION = 20
const DURATION_STEP = 2

const visualizerBars = [
  48, 88, 126, 72, 150, 104, 56, 132, 92, 164, 70, 116, 154, 82, 46, 122, 96, 142, 66, 110, 158, 76,
]

function normalizeApiUrl(baseUrl, path) {
  return `${baseUrl.replace(/\/$/, '')}${path}`
}

function clampDuration(value) {
  return Math.min(MAX_DURATION, Math.max(MIN_DURATION, value))
}

function DurationControl({ duration, setDuration }) {
  return (
    <section className="duration-control" aria-labelledby="duration-title">
      <div>
        <p className="control-label" id="duration-title">
          Duracao
        </p>
        <p className="duration-value">{duration}s</p>
      </div>

      <div className="duration-row">
        <button
          type="button"
          className="icon-button"
          onClick={() => setDuration((currentDuration) => clampDuration(currentDuration - DURATION_STEP))}
          disabled={duration <= MIN_DURATION}
          aria-label="Diminuir duracao"
        >
          -
        </button>
        <input
          type="range"
          min={MIN_DURATION}
          max={MAX_DURATION}
          step={DURATION_STEP}
          value={duration}
          onChange={(event) => setDuration(Number(event.target.value))}
          aria-label="Duracao em segundos"
        />
        <button
          type="button"
          className="icon-button"
          onClick={() => setDuration((currentDuration) => clampDuration(currentDuration + DURATION_STEP))}
          disabled={duration >= MAX_DURATION}
          aria-label="Aumentar duracao"
        >
          +
        </button>
      </div>
    </section>
  )
}

function PlayerPanel({ status, audioUrl, title, copy, outputFormat = 'WAV' }) {
  return (
    <aside className="player-panel" aria-label="Resultado">
      <div className="visualizer" aria-hidden="true">
        {visualizerBars.map((height, index) => (
          <span key={`${height}-${index}`} style={{ '--bar-index': index, '--bar-height': `${height}px` }} />
        ))}
      </div>

      <div className="status-area">
        <p className="status-label">
          {status === 'loading'
            ? 'A gerar'
            : status === 'success'
              ? 'Audio pronto'
              : status === 'error'
                ? 'Erro'
                : 'Pronto'}
        </p>
        <h2>{title}</h2>
        <p className="status-copy">{copy}</p>
      </div>

      {audioUrl ? (
        <audio className="audio-player" controls src={audioUrl}>
          O teu browser nao suporta reproducao de audio.
        </audio>
      ) : (
        <div className="empty-player" aria-hidden="true">
          {outputFormat}
        </div>
      )}
    </aside>
  )
}

function HomePage({ onSelectMode }) {
  return (
    <main className="app-shell">
      <section className="home-page" aria-labelledby="home-title">
        <p className="eyebrow">MusicGen Studio</p>
        <h1 id="home-title">Mc Mozart</h1>
        <div className="mode-actions" aria-label="Escolher modo de geracao">
          <button type="button" className="mode-button" onClick={() => onSelectMode('lyrics')}>
            Letra de musica
          </button>
          <button type="button" className="mode-button" onClick={() => onSelectMode('music')}>
            So musica
          </button>
        </div>
      </section>
    </main>
  )
}

function MusicPage({ onBack }) {
  const [prompt, setPrompt] = useState('')
  const [duration, setDuration] = useState(8)
  const [audioUrl, setAudioUrl] = useState('')
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState('')
  const [lastPrompt, setLastPrompt] = useState('')

  const cleanPrompt = prompt.trim()

  async function handleSubmit(event) {
    event.preventDefault()

    if (!cleanPrompt) {
      setError('Escreve uma prompt antes de gerar.')
      return
    }

    setStatus('loading')
    setError('')
    setAudioUrl('')
    setLastPrompt(cleanPrompt)

    try {
      const response = await fetch(normalizeApiUrl(API_BASE_URL, '/generate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: cleanPrompt,
          duration_seconds: duration,
        }),
      })

      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(data.detail || 'Nao foi possivel gerar o audio.')
      }

      const generatedUrl =
        data.audio_url || data.audioUrl || (data.file ? normalizeApiUrl(API_BASE_URL, `/audio/${data.file}`) : '')

      if (!generatedUrl) {
        throw new Error('A API nao devolveu o endereco do audio.')
      }

      setAudioUrl(generatedUrl)
      setStatus('success')
    } catch (requestError) {
      setStatus('error')
      setError(requestError.message)
    }
  }

  return (
    <main className="app-shell">
      <section className="workspace" aria-labelledby="page-title">
        <div className="composer">
          <header className="composer-header">
            <button type="button" className="back-button" onClick={onBack}>
              Voltar
            </button>
            <p className="eyebrow">Mc Mozart</p>
            <h1 id="page-title">So musica</h1>
          </header>

          <form className="composer-form" onSubmit={handleSubmit}>
            <label className="field">
              <span>Prompt</span>
              <textarea
                value={prompt}
                onChange={(event) => {
                  setPrompt(event.target.value)
                  setError('')
                }}
                rows="7"
                placeholder="Ex.: funk pesado com baixo forte e bateria rapida"
              />
            </label>

            <DurationControl duration={duration} setDuration={setDuration} />

            <div className="actions">
              <button className="primary-action" type="submit" disabled={status === 'loading'}>
                <span aria-hidden="true">{status === 'loading' ? '...' : '>'}</span>
                {status === 'loading' ? 'A gerar audio' : 'Gerar musica'}
              </button>
            </div>
          </form>
        </div>

        <PlayerPanel
          status={status}
          audioUrl={audioUrl}
          title={status === 'success' ? 'Resultado gerado' : 'Nova composicao'}
          copy={
            status === 'loading'
              ? `A criar cerca de ${duration} segundos de audio.`
              : status === 'success'
                ? `${lastPrompt} - ${duration}s`
                : status === 'error'
                  ? error
                  : 'Escreve uma prompt, escolhe a duracao e gera o audio.'
          }
        />
      </section>
    </main>
  )
}

function LyricsPage({ onBack }) {
  const [musicPrompt, setMusicPrompt] = useState('')
  const [lyrics, setLyrics] = useState('')
  const [duration, setDuration] = useState(8)
  const [audioUrl, setAudioUrl] = useState('')
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState('')
  const [lastPrompt, setLastPrompt] = useState('')

  const cleanMusicPrompt = musicPrompt.trim()
  const cleanLyrics = lyrics.trim()

  async function handleSubmit(event) {
    event.preventDefault()

    if (!cleanMusicPrompt || !cleanLyrics) {
      setError('Escreve uma prompt e uma letra antes de gerar.')
      return
    }

    setStatus('loading')
    setError('')
    setAudioUrl('')
    setLastPrompt(cleanMusicPrompt)

    try {
      const response = await fetch(normalizeApiUrl(API_BASE_URL, '/generate-with-speech'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          music_prompt: cleanMusicPrompt,
          lyrics: cleanLyrics,
          duration_seconds: duration,
          speech_engine: 'piper',
          language: 'pt-PT',
        }),
      })

      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(data.detail || 'Nao foi possivel gerar o audio com letra.')
      }

      const generatedUrl =
        data.audio_url || data.audioUrl || (data.file ? normalizeApiUrl(API_BASE_URL, `/audio/${data.file}`) : '')

      if (!generatedUrl) {
        throw new Error('A API nao devolveu o endereco do audio.')
      }

      setAudioUrl(generatedUrl)
      setStatus('success')
    } catch (requestError) {
      setStatus('error')
      setError(requestError.message)
    }
  }

  return (
    <main className="app-shell">
      <section className="workspace" aria-labelledby="lyrics-page-title">
        <div className="composer">
          <header className="composer-header">
            <button type="button" className="back-button" onClick={onBack}>
              Voltar
            </button>
            <p className="eyebrow">Mc Mozart</p>
            <h1 id="lyrics-page-title">Letra de musica</h1>
          </header>

          <form className="composer-form" onSubmit={handleSubmit}>
            <label className="field">
              <span>Prompt da musica</span>
              <textarea
                value={musicPrompt}
                onChange={(event) => {
                  setMusicPrompt(event.target.value)
                  setError('')
                }}
                rows="4"
                placeholder="Ex.: boom bap calmo com piano suave"
              />
            </label>

            <label className="field">
              <span>Letra</span>
              <textarea
                value={lyrics}
                onChange={(event) => {
                  setLyrics(event.target.value)
                  setError('')
                }}
                rows="6"
                placeholder="Escreve aqui a letra da musica"
              />
            </label>

            <DurationControl duration={duration} setDuration={setDuration} />

            <div className="actions">
              <button className="primary-action" type="submit" disabled={status === 'loading'}>
                <span aria-hidden="true">{status === 'loading' ? '...' : '>'}</span>
                {status === 'loading' ? 'A gerar audio' : 'Gerar com letra'}
              </button>
            </div>
          </form>
        </div>

        <PlayerPanel
          status={status}
          audioUrl={audioUrl}
          title={status === 'success' ? 'Resultado gerado' : 'Nova musica com letra'}
          copy={
            status === 'loading'
              ? `A criar cerca de ${duration} segundos de audio.`
              : status === 'success'
                ? `${lastPrompt} - ${duration}s`
                : status === 'error'
                  ? error
                  : 'Escreve a prompt da musica, a letra e gera o audio.'
          }
          outputFormat="MP3"
        />
      </section>
    </main>
  )
}

function App() {
  const [page, setPage] = useState('home')

  if (page === 'music') {
    return <MusicPage onBack={() => setPage('home')} />
  }

  if (page === 'lyrics') {
    return <LyricsPage onBack={() => setPage('home')} />
  }

  return <HomePage onSelectMode={setPage} />
}

export default App
