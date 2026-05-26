// frontend/src/components/Dashboard/ChartPanel.jsx
import { useState, useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'

const CHART_TYPE_BADGE = {
  histogram:   { label: 'Distribution', color: 'bg-blue-900/40 text-blue-300 border-blue-800' },
  box:         { label: 'Box plot',     color: 'bg-purple-900/40 text-purple-300 border-purple-800' },
  bar:         { label: 'Bar chart',    color: 'bg-teal-900/40 text-teal-300 border-teal-800' },
  scatter:     { label: 'Scatter',      color: 'bg-amber-900/40 text-amber-300 border-amber-800' },
  line:        { label: 'Time series',  color: 'bg-green-900/40 text-green-300 border-green-800' },
  heatmap:     { label: 'Heatmap',      color: 'bg-red-900/40 text-red-300 border-red-800' },
  pca_scatter: { label: 'PCA',          color: 'bg-indigo-900/40 text-indigo-300 border-indigo-800' },
  gauge:       { label: 'Quality',      color: 'bg-gray-800 text-gray-400 border-gray-700' },
}

// ── Direct Plotly renderer — no react-plotly.js dependency ───────
// We use Plotly.js directly via useEffect to avoid the lazy/CJS
// interop issues with react-plotly.js
function PlotlyChart({ data, layout, chartId, height }) {
  const containerRef = useRef(null)
  const plotRef      = useRef(null)

  const mergedLayout = {
    ...layout,
    height,
    autosize:     true,
    paper_bgcolor:'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
  }

  // Initial render
  useEffect(() => {
    if (!containerRef.current) return
    let cancelled = false

    Plotly.newPlot(
      containerRef.current,
      data,
      mergedLayout,
      {
        responsive:  true,
        displaylogo: false,
        modeBarButtonsToRemove: ['select2d', 'lasso2d', 'autoScale2d'],
        toImageButtonOptions: {
          format:   'png',
          filename: chartId,
          scale:    2,
        },
      }
    ).then(plot => {
      if (!cancelled) plotRef.current = plot
    })

    return () => {
      cancelled = true
      if (containerRef.current) {
        Plotly.purge(containerRef.current)
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartId])

  // React to height changes (expand/collapse)
  useEffect(() => {
    if (!containerRef.current) return
    Plotly.relayout(containerRef.current, { height })
  }, [height])

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', minHeight: height }}
    />
  )
}

export default function ChartPanel({ chart, fullWidth = false }) {
  const [expanded, setExpanded] = useState(false)
  const [ready, setReady]       = useState(false)

  const badge = CHART_TYPE_BADGE[chart.chart_type] || {
    label: chart.chart_type,
    color: 'bg-gray-800 text-gray-400 border-gray-700',
  }

  const chartHeight =
    chart.chart_type === 'gauge'   ? 220 :
    chart.chart_type === 'heatmap' ? Math.max(300, (chart.columns?.length ?? 6) * 32) :
    expanded ? 480 : 300

  // Slight delay so the panel animates in before Plotly renders
  // (prevents layout-thrashing on bulk dashboard load)
  useEffect(() => {
    const t = setTimeout(() => setReady(true), 60)
    return () => clearTimeout(t)
  }, [])

  return (
    <div
      className={[
        'bg-gray-800/50 border border-gray-700/50 rounded-2xl overflow-hidden flex flex-col',
        fullWidth  ? 'xl:col-span-2' : '',
        expanded   ? 'xl:col-span-2' : '',
      ].join(' ')}
    >
      {/* ── Panel header ── */}
      <div className="flex items-start justify-between gap-3 px-4 pt-4 pb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 ${badge.color}`}>
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
          className="shrink-0 text-gray-600 hover:text-gray-400 transition-colors p-1 rounded"
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

      {/* ── Chart ── */}
      <div className="px-2 pb-3">
        {ready ? (
          <PlotlyChart
            data={chart.plotly_data}
            layout={chart.plotly_layout}
            chartId={chart.chart_id}
            height={chartHeight}
          />
        ) : (
          <div
            className="flex items-center justify-center bg-gray-900/40 rounded-xl"
            style={{ height: chartHeight }}
          >
            <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent
                            rounded-full animate-spin" />
          </div>
        )}
      </div>

      {/* ── Source columns ── */}
      {chart.columns?.length > 0 && (
        <div className="px-4 pb-3 flex flex-wrap gap-1">
          {chart.columns.slice(0, 6).map(col => (
            <span
              key={col}
              className="text-xs font-mono text-gray-600 bg-gray-900
                         px-1.5 py-0.5 rounded border border-gray-800"
            >
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