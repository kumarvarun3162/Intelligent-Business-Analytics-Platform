// frontend/src/components/Dashboard/ChartPanel.jsx
import { useState, lazy, Suspense } from 'react'

const Plot = lazy(() =>
  import('react-plotly.js').then(mod => ({
    default: mod.default
  }))
)

const CHART_TYPE_BADGE = {
  histogram:   { label: 'Distribution', color: 'bg-blue-900/40 text-blue-300 border-blue-800' },
  box:         { label: 'Box plot',     color: 'bg-purple-900/40 text-purple-300 border-purple-800' },
  bar:         { label: 'Bar chart',    color: 'bg-teal-900/40 text-teal-300 border-teal-800' },
  scatter:     { label: 'Scatter',      color: 'bg-amber-900/40 text-amber-300 border-amber-800' },
  line:        { label: 'Time series',  color: 'bg-green-900/40 text-green-300 border-green-800' },
  heatmap:     { label: 'Heatmap',      color: 'bg-coral-900/40 text-coral-300 border-coral-800' },
  pca_scatter: { label: 'PCA',          color: 'bg-indigo-900/40 text-indigo-300 border-indigo-800' },
  gauge:       { label: 'Quality',      color: 'bg-gray-800 text-gray-400 border-gray-700' },
}

export default function ChartPanel({ chart, fullWidth = false }) {
  const [expanded, setExpanded] = useState(false)
  const badge = CHART_TYPE_BADGE[chart.chart_type] || {
    label: chart.chart_type, color: 'bg-gray-800 text-gray-400 border-gray-700'
  }

  // Plotly responsive config — makes charts resize with their container
  const config = {
    responsive:  true,
    displaylogo: false,
    modeBarButtonsToRemove: ['select2d', 'lasso2d', 'autoScale2d'],
    toImageButtonOptions: {
      format: 'png', filename: chart.chart_id, scale: 2,
    },
  }

  return (
    <div
      className={`bg-gray-800/50 border border-gray-700/50 rounded-2xl
                  overflow-hidden flex flex-col
                  ${fullWidth ? 'xl:col-span-2' : ''}
                  ${expanded ? 'xl:col-span-2' : ''}`}
    >
      {/* Panel header */}
      <div className="flex items-start justify-between gap-3 px-4 pt-4 pb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0
                             ${badge.color}`}>
              {badge.label}
            </span>
          </div>
          <h3 className="text-white text-sm font-medium truncate">
            {chart.title}
          </h3>
          {chart.insight && (
            <p className="text-gray-500 text-xs mt-0.5 line-clamp-2">
              {chart.insight}
            </p>
          )}
        </div>
        <button
          onClick={() => setExpanded(e => !e)}
          className="shrink-0 text-gray-600 hover:text-gray-400
                     transition-colors p-1 rounded"
          title={expanded ? 'Collapse' : 'Expand'}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            {expanded
              ? <path d="M2 9l5-5 5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              : <path d="M2 5l5 5 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            }
          </svg>
        </button>
      </div>

      {/* Plotly chart */}
      <div className="px-2 pb-3">
        <Suspense fallback={
          <div className="h-48 flex items-center justify-center">
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent
                            rounded-full animate-spin" />
          </div>
        }>
          <Plot
            data={chart.plotly_data}
            layout={{
              ...chart.plotly_layout,
              height: chart.chart_type === 'gauge'  ? 200
                    : chart.chart_type === 'heatmap' ? undefined
                    : expanded ? 480 : 300,
              autosize: true,
            }}
            config={config}
            style={{ width: '100%' }}
            useResizeHandler
          />
        </Suspense>
      </div>

      {/* Columns used */}
      {chart.columns.length > 0 && (
        <div className="px-4 pb-3 flex flex-wrap gap-1">
          {chart.columns.slice(0, 6).map(col => (
            <span key={col}
              className="text-xs font-mono text-gray-600 bg-gray-900
                         px-1.5 py-0.5 rounded border border-gray-800">
              {col}
            </span>
          ))}
          {chart.columns.length > 6 && (
            <span className="text-xs text-gray-700">
              +{chart.columns.length - 6} more
            </span>
          )}
        </div>
      )}
    </div>
  )
}