// frontend/src/components/Dashboard/Dashboard.jsx
import { useState, useCallback } from 'react'
import axios from 'axios'
import ChartPanel from './ChartPanel'
import DashboardHeader from './DashboardHeader'
import API_BASE from '../../api/config'

const CHART_TYPE_LABELS = {
  all:         'All charts',
  histogram:   'Distributions',
  box:         'Box plots',
  bar:         'Categories',
  scatter:     'Scatter',
  line:        'Time series',
  heatmap:     'Heatmap',
  pca_scatter: 'PCA',
  gauge:       'Quality',
}

export default function Dashboard({ sessionId }) {
  const [loading,   setLoading]   = useState(false)
  const [dashboard, setDashboard] = useState(null)
  const [error,     setError]     = useState(null)
  const [filter,    setFilter]    = useState('all')

  const generate = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await axios.post(`${API_BASE}/api/charts`, {
        session_id: sessionId,
      })
      setDashboard(res.data.dashboard)
    } catch (err) {
      setError(err.response?.data?.detail || 'Dashboard generation failed.')
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  const visibleCharts = dashboard?.charts.filter(c =>
    filter === 'all' || c.chart_type === filter
  ) ?? []

  const chartTypeCount = dashboard?.charts.reduce((acc, c) => {
    acc[c.chart_type] = (acc[c.chart_type] || 0) + 1
    return acc
  }, {}) ?? {}

  return (
    <div className="bg-gray-900 rounded-2xl border border-gray-800 overflow-hidden">

      {/* ── Header ── */}
      <div className="p-6 border-b border-gray-800">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-white">
              Interactive dashboard
            </h2>
            <p className="text-gray-500 text-sm mt-1">
              Auto-generated charts from your data
            </p>
          </div>
          <button
            onClick={generate}
            disabled={loading}
            className="shrink-0 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700
                       text-white text-sm font-medium px-5 py-2.5 rounded-xl
                       transition-colors"
          >
            {loading ? 'Generating…' : dashboard ? 'Regenerate' : 'Generate dashboard'}
          </button>
        </div>
      </div>

      {/* ── Error ── */}
      {error && (
        <div className="px-6 py-4 bg-red-900/20 border-b border-red-800/40">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {/* ── Loading spinner ── */}
      {loading && (
        <div className="p-12 flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent
                          rounded-full animate-spin" />
          <p className="text-gray-400 text-sm">Building charts…</p>
        </div>
      )}

      {/* ── Dashboard content ── */}
      {dashboard && !loading && (
        <>
          <DashboardHeader dashboard={dashboard} />

          {/* Filter tabs */}
          <div className="px-6 py-3 border-b border-gray-800 flex gap-1 flex-wrap">
            {Object.entries(CHART_TYPE_LABELS).map(([type, label]) => {
              const count = type === 'all'
                ? dashboard.charts.length
                : (chartTypeCount[type] || 0)
              if (type !== 'all' && count === 0) return null
              return (
                <button
                  key={type}
                  onClick={() => setFilter(type)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition-colors
                    ${filter === type
                      ? 'bg-gray-700 text-white'
                      : 'text-gray-500 hover:text-gray-300'}`}
                >
                  {label}
                  {count > 0 && (
                    <span className="ml-1.5 text-xs opacity-60">{count}</span>
                  )}
                </button>
              )
            })}
          </div>

          {/* Chart grid */}
          <div className="p-6">
            {visibleCharts.length === 0 ? (
              <p className="text-gray-600 text-sm text-center py-8">
                No charts of this type in the current dashboard.
              </p>
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {visibleCharts.map((chart) => (
                  <ChartPanel
                    key={chart.chart_id}
                    chart={chart}
                    fullWidth={
                      chart.chart_type === 'heatmap'     ||
                      chart.chart_type === 'line'        ||
                      chart.chart_type === 'pca_scatter'
                    }
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}