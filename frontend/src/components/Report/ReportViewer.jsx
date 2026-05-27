// frontend/src/components/Report/ReportViewer.jsx
import { useState } from 'react'
import axios from 'axios'

const API_BASE = 'http://localhost:8080'

function NarrativeCard({ section }) {
  const [expanded, setExpanded] = useState(true)
  return (
    <div className="bg-gray-800/50 border border-gray-700/50 rounded-2xl overflow-hidden">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between px-5 py-4
                   hover:bg-gray-800 transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          <span className="text-xl">{section.emoji}</span>
          <span className="text-white font-medium">{section.title}</span>
        </div>
        <svg
          width="14" height="14" viewBox="0 0 14 14" fill="none"
          className={`text-gray-500 transition-transform ${expanded ? '' : '-rotate-90'}`}
        >
          <path d="M2 5l5 5 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      </button>
      {expanded && (
        <div className="px-5 pb-5">
          <p className="text-gray-300 leading-relaxed text-sm">
            {section.content}
          </p>
        </div>
      )}
    </div>
  )
}

function PassportStage({ stage }) {
  const colors = {
    1: 'bg-blue-900/40 text-blue-300 border-blue-800',
    2: 'bg-teal-900/40 text-teal-300 border-teal-800',
    3: 'bg-purple-900/40 text-purple-300 border-purple-800',
    4: 'bg-amber-900/40 text-amber-300 border-amber-800',
  }
  const c = colors[stage.phase] || 'bg-gray-800 text-gray-400 border-gray-700'

  return (
    <div className={`border rounded-xl px-4 py-3 ${c}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-bold opacity-70">
          Phase {stage.phase}
        </span>
        <span className="font-medium text-sm">{stage.name}</span>
        {stage.quality_grade && (
          <span className="ml-auto text-xs font-mono opacity-80">
            Grade {stage.quality_grade} · {stage.quality_score}/100
          </span>
        )}
      </div>
      <p className="text-xs opacity-70">{stage.summary}</p>
    </div>
  )
}

function DownloadButton({ label, icon, href, color }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className={`flex items-center gap-2 px-4 py-3 rounded-xl
                  text-sm font-medium transition-colors ${color}`}
    >
      <span className="text-base">{icon}</span>
      {label}
    </a>
  )
}

export default function ReportViewer({ sessionId }) {
  const [loading, setLoading] = useState(false)
  const [report,  setReport]  = useState(null)
  const [error,   setError]   = useState(null)
  const [tab,     setTab]     = useState('narrative')

  const handleGenerate = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await axios.post(`${API_BASE}/api/report/generate`, {
        session_id: sessionId,
      })
      setReport(res.data.report)
    } catch (err) {
      const detail = err.response?.data?.detail || 'Report generation failed.'
      setError(detail)
    } finally {
      setLoading(false)
    }
  }

  const handleStream = async () => {
    setLoading(true)
    setError(null)
    // Build an empty report shell to stream into
    const streamingReport = {
      dataset_name:  'Streaming…',
      generated_at:  new Date().toISOString(),
      model_used:    'llama-3.3-70b-versatile',
      narrative:     [],
      data_passport: null,
      download_urls: {},
    }
    setReport(streamingReport)
    try {
      const response = await fetch(`${API_BASE}/api/report/stream`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ session_id: sessionId }),
      })
      const reader  = response.body.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text  = decoder.decode(value)
        const lines = text.split('\n').filter(l => l.startsWith('data: '))
        for (const line of lines) {
          try {
            const payload = JSON.parse(line.slice(6))
            if (payload.done) {
              setLoading(false)
              break
            }
            if (payload.section_done) {
              setReport(prev => ({
                ...prev,
                narrative: [
                  ...(prev.narrative || []),
                  {
                    section: payload.section,
                    title:   payload.title,
                    emoji:   payload.emoji,
                    content: payload.content,
                  },
                ],
              }))
            }
          } catch (_) {}
        }
      }
    } catch (err) {
      setError('Streaming failed: ' + err.message)
    } finally {
      setLoading(false)
    }
  }

  const passport = report?.data_passport

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">

      {/* Header */}
      <div className="p-6 border-b border-gray-800">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-white">
              Automated report
            </h2>
            <p className="text-gray-500 text-sm mt-1">
              LLM-narrated analysis · PDF export · data passport · ML-ready CSV
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={handleStream}
              disabled={loading}
              className="bg-purple-700 hover:bg-purple-600 disabled:bg-gray-700
                         text-white text-sm font-medium px-4 py-2.5 rounded-xl
                         transition-colors"
            >
              {loading ? '…' : '⚡ Stream'}
            </button>
            <button
              onClick={handleGenerate}
              disabled={loading}
              className="bg-teal-700 hover:bg-teal-600 disabled:bg-gray-700
                         text-white text-sm font-medium px-4 py-2.5 rounded-xl
                         transition-colors"
            >
              {loading ? 'Generating…' : report ? 'Regenerate' : 'Generate'}
            </button>
          </div>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="p-10 flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-teal-500 border-t-transparent
                          rounded-full animate-spin" />
          <div className="text-center">
            <p className="text-white font-medium">Generating your report</p>
            <p className="text-gray-500 text-sm mt-1">
              The LLM is narrating your data — this takes 10–30 seconds
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="px-6 py-4 bg-red-900/20 border-b border-red-800/40">
          <p className="text-red-400 text-sm">{error}</p>
          {error.includes('GROQ_API_KEY') && (
            <p className="text-gray-500 text-xs mt-1">
              Get a free key at{' '}
              <a href="https://console.groq.com"
                 target="_blank" rel="noreferrer"
                 className="text-teal-400 underline">
                console.groq.com
              </a>
            </p>
          )}
        </div>
      )}

      {report && !loading && (
        <>
          {/* Report meta bar */}
          <div className="px-6 py-3 bg-gray-800/40 border-b border-gray-800
                          flex items-center gap-6 flex-wrap text-sm">
            <div>
              <span className="text-gray-500">Dataset: </span>
              <span className="text-white">{report.dataset_name}</span>
            </div>
            {passport?.quality_score != null && (
              <div>
                <span className="text-gray-500">Quality: </span>
                <span className={`font-bold ${
                  passport.quality_score >= 75 ? 'text-teal-400' :
                  passport.quality_score >= 50 ? 'text-amber-400' :
                  'text-red-400'
                }`}>
                  {passport.quality_score}/100 (Grade {passport.quality_grade})
                </span>
              </div>
            )}
            <div>
              <span className="text-gray-500">Model: </span>
              <span className="text-gray-300 font-mono text-xs">
                {report.model_used}
              </span>
            </div>
            <div className="text-gray-600 text-xs ml-auto">
              {new Date(report.generated_at).toLocaleString()}
            </div>
          </div>

          {/* Tabs */}
          <div className="px-6 py-3 border-b border-gray-800 flex gap-1">
            {[
              { id: 'narrative', label: 'Narrative' },
              { id: 'passport',  label: 'Data passport' },
              { id: 'downloads', label: 'Downloads' },
            ].map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3 py-1.5 rounded-lg text-sm transition-colors
                  ${tab === t.id
                    ? 'bg-gray-700 text-white'
                    : 'text-gray-500 hover:text-gray-300'}`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Tab: Narrative */}
          {tab === 'narrative' && (
            <div className="p-6 space-y-4">
              {report.narrative.map((sec, i) => (
                <NarrativeCard key={i} section={sec} />
              ))}
            </div>
          )}

          {/* Tab: Data passport */}
          {tab === 'passport' && passport && (
            <div className="p-6 space-y-6">

              {/* Summary stats */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  ['Total transforms',  passport.total_transforms],
                  ['Cleaning actions',  passport.cleaning_actions],
                  ['New features',      passport.new_features],
                  ['ML ready',          passport.ml_ready ? 'Yes' : 'No'],
                ].map(([label, val]) => (
                  <div key={label}
                    className="bg-gray-800 rounded-xl p-3 text-center">
                    <p className={`text-xl font-bold ${
                      label === 'ML ready'
                        ? val === 'Yes' ? 'text-teal-400' : 'text-amber-400'
                        : 'text-white'
                    }`}>{val}</p>
                    <p className="text-gray-500 text-xs mt-1">{label}</p>
                  </div>
                ))}
              </div>

              {/* Pipeline stages */}
              <div>
                <p className="text-xs uppercase tracking-wide text-gray-500 mb-3">
                  Pipeline stages
                </p>
                <div className="space-y-2">
                  {passport.pipeline_stages.map((stage, i) => (
                    <PassportStage key={i} stage={stage} />
                  ))}
                </div>
              </div>

              {/* Column lineage */}
              {Object.keys(passport.column_lineage).length > 0 && (
                <div>
                  <p className="text-xs uppercase tracking-wide text-gray-500 mb-3">
                    Column lineage — derived features
                  </p>
                  <div className="space-y-1 max-h-64 overflow-y-auto pr-1">
                    {Object.entries(passport.column_lineage)
                      .slice(0, 30)
                      .map(([col, origin]) => (
                        <div key={col}
                          className="flex items-start gap-3 text-xs
                                     bg-gray-800 rounded-lg px-3 py-2">
                          <span className="font-mono text-purple-300 shrink-0 w-36 truncate">
                            {col}
                          </span>
                          <span className="text-gray-500">{origin}</span>
                        </div>
                      ))
                    }
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab: Downloads */}
          {tab === 'downloads' && (
            <div className="p-6 space-y-4">
              <p className="text-gray-500 text-sm">
                Download your processed data and report files.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <DownloadButton
                  label="PDF report"
                  icon="📄"
                  href={report.download_urls.pdf}
                  color="bg-red-900/30 hover:bg-red-900/50 text-red-300 border border-red-800"
                />
                <DownloadButton
                  label="ML-ready CSV"
                  icon="📊"
                  href={report.download_urls.csv}
                  color="bg-teal-900/30 hover:bg-teal-900/50 text-teal-300 border border-teal-800"
                />
                <DownloadButton
                  label="Data passport JSON"
                  icon="🗂️"
                  href={report.download_urls.passport}
                  color="bg-purple-900/30 hover:bg-purple-900/50 text-purple-300 border border-purple-800"
                />
              </div>

              <div className="bg-gray-800 rounded-xl p-4 space-y-2">
                <p className="text-white text-sm font-medium">What's in each file</p>
                <div className="text-xs text-gray-400 space-y-1.5">
                  <p><span className="text-red-300 font-medium">PDF report</span> — full narrative, statistical tables, pipeline audit, A4 formatted</p>
                  <p><span className="text-teal-300 font-medium">ML-ready CSV</span> — cleaned + engineered dataset, all nulls filled, all columns numeric</p>
                  <p><span className="text-purple-300 font-medium">Data passport</span> — JSON audit of every transform, column lineage, reproducibility record</p>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}