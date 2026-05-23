// frontend/src/components/Analysis/InsightsPanel.jsx
import { useState } from 'react'
import axios from 'axios'

const API_BASE = 'http://localhost:8080'

function StatCard({ stat }) {
  const isSkewed = Math.abs(stat.skewness) > 1
  const isNonNormal = !stat.is_normal

  return (
    <div className="bg-gray-800 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between">
        <p className="text-white font-medium text-sm truncate max-w-[160px]">
          {stat.column}
        </p>
        <div className="flex gap-1 shrink-0">
          {isSkewed && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-amber-900/40
                             text-amber-300 border border-amber-800">
              skewed
            </span>
          )}
          {isNonNormal && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-purple-900/40
                             text-purple-300 border border-purple-800">
              non-normal
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        {[
          ['mean',   stat.mean],
          ['median', stat.median],
          ['std',    stat.std],
          ['min',    stat.min],
          ['max',    stat.max],
          ['IQR',    stat.iqr],
          ['skew',   stat.skewness],
          ['kurt',   stat.kurtosis],
          ['CV',     stat.cv],
        ].map(([label, val]) => (
          <div key={label} className="bg-gray-900 rounded-lg px-2 py-1.5">
            <p className="text-gray-500 uppercase tracking-wide text-[10px]">
              {label}
            </p>
            <p className="text-gray-200 font-mono mt-0.5">
              {typeof val === 'number' ? val.toFixed(3) : val}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}

function CorrelationRow({ pair }) {
  const strength = {
    strong:     'text-red-400',
    moderate:   'text-amber-400',
    weak:       'text-yellow-400',
    negligible: 'text-gray-500',
  }
  const barWidth = Math.abs(pair.pearson) * 100
  const barColor = pair.pearson > 0 ? 'bg-teal-500' : 'bg-coral-500'

  return (
    <div className="flex items-center gap-3 py-2 border-b border-gray-800 text-sm">
      <span className="text-gray-400 font-mono w-36 truncate">{pair.col_a}</span>
      <span className="text-gray-600 text-xs">↔</span>
      <span className="text-gray-400 font-mono w-36 truncate">{pair.col_b}</span>
      <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${pair.pearson > 0 ? 'bg-teal-500' : 'bg-red-500'}`}
          style={{ width: `${barWidth}%` }}
        />
      </div>
      <span className={`font-mono text-xs w-12 text-right ${strength[pair.strength]}`}>
        {pair.pearson > 0 ? '+' : ''}{pair.pearson.toFixed(3)}
      </span>
      <span className="text-gray-600 text-xs w-16">{pair.strength}</span>
    </div>
  )
}

export default function InsightsPanel({ sessionId }) {
  const [loading, setLoading] = useState(false)
  const [report, setReport]   = useState(null)
  const [error, setError]     = useState(null)
  const [tab, setTab]         = useState('insights')

  const handleAnalyze = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await axios.post(`${API_BASE}/api/analyze`, {
        session_id:     sessionId,
        use_engineered: true,
      })
      setReport(res.data.report)
    } catch (err) {
      setError(err.response?.data?.detail || 'Analysis failed.')
    } finally {
      setLoading(false)
    }
  }

  const TABS = [
    { id: 'insights',      label: 'Insights' },
    { id: 'descriptive',   label: 'Descriptive' },
    { id: 'correlations',  label: 'Correlations' },
    { id: 'distributions', label: 'Distributions' },
    { id: 'hypothesis',    label: 'Hypothesis tests' },
    { id: 'pca',           label: 'PCA' },
  ]

  return (
    <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">Statistical analysis</h2>
        <p className="text-gray-500 text-sm mt-1">
          EDA, correlations, hypothesis tests, PCA — all automated
        </p>
      </div>

      <button
        onClick={handleAnalyze}
        disabled={loading}
        className="w-full bg-teal-700 hover:bg-teal-600 disabled:bg-gray-700
                   text-white font-medium py-3 rounded-xl transition-colors"
      >
        {loading ? 'Analysing your data…' : 'Run statistical analysis'}
      </button>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {report && (
        <>
          {/* Summary bar */}
          <div className="grid grid-cols-4 gap-3">
            {[
              ['Columns analysed', report.descriptive.length],
              ['Correlations',     report.correlations.length],
              ['Key insights',     report.key_insights.length],
              ['Warnings',         report.warnings.length],
            ].map(([label, val]) => (
              <div key={label} className="bg-gray-800 rounded-xl p-3 text-center">
                <p className="text-2xl font-bold text-white">{val}</p>
                <p className="text-gray-500 text-xs mt-1">{label}</p>
              </div>
            ))}
          </div>

          {/* Tabs */}
          <div className="flex gap-1 flex-wrap">
            {TABS.map(t => (
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

          {/* Tab: Insights */}
          {tab === 'insights' && (
            <div className="space-y-4">
              {report.warnings.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs uppercase tracking-wide text-amber-400">
                    Warnings
                  </p>
                  {report.warnings.map((w, i) => (
                    <div key={i}
                      className="bg-amber-900/20 border border-amber-800/50
                                 rounded-xl px-4 py-3 text-amber-200 text-sm">
                      {w}
                    </div>
                  ))}
                </div>
              )}
              <div className="space-y-2">
                <p className="text-xs uppercase tracking-wide text-teal-400">
                  Key insights
                </p>
                {report.key_insights.length === 0 && (
                  <p className="text-gray-500 text-sm">
                    No significant insights detected. Data looks clean.
                  </p>
                )}
                {report.key_insights.map((ins, i) => (
                  <div key={i}
                    className="bg-teal-900/20 border border-teal-800/50
                               rounded-xl px-4 py-3 text-teal-100 text-sm">
                    {ins}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tab: Descriptive */}
          {tab === 'descriptive' && (
            <div className="grid grid-cols-1 gap-4">
              {report.descriptive.map((s, i) => (
                <StatCard key={i} stat={s} />
              ))}
            </div>
          )}

          {/* Tab: Correlations */}
          {tab === 'correlations' && (
            <div>
              {report.correlations.length === 0 ? (
                <p className="text-gray-500 text-sm">
                  No significant correlations (|r| ≥ 0.2) found.
                </p>
              ) : (
                <div>
                  <div className="flex gap-3 text-xs text-gray-600 pb-2
                                  border-b border-gray-800 mb-1">
                    <span className="w-36">Column A</span>
                    <span className="w-4"></span>
                    <span className="w-36">Column B</span>
                    <span className="flex-1">Pearson r</span>
                    <span className="w-12 text-right">r</span>
                    <span className="w-16">Strength</span>
                  </div>
                  {report.correlations.map((pair, i) => (
                    <CorrelationRow key={i} pair={pair} />
                  ))}
                </div>
              )}

              {/* VIF table */}
              {report.vif_results.length > 0 && (
                <div className="mt-6">
                  <p className="text-xs uppercase tracking-wide text-gray-500 mb-3">
                    Variance inflation factors
                  </p>
                  <div className="space-y-1">
                    {report.vif_results.map((v, i) => (
                      <div key={i}
                        className="flex items-center gap-3 text-sm py-1.5
                                   border-b border-gray-800">
                        <span className="text-gray-400 font-mono w-40 truncate">
                          {v.column}
                        </span>
                        <span className={`font-mono ${
                          v.flag === 'severe'   ? 'text-red-400'   :
                          v.flag === 'moderate' ? 'text-amber-400' :
                          'text-green-400'
                        }`}>
                          {v.vif.toFixed(2)}
                        </span>
                        <span className={`text-xs px-2 py-0.5 rounded-full border ${
                          v.flag === 'severe'
                            ? 'bg-red-900/40 text-red-300 border-red-800'
                            : v.flag === 'moderate'
                            ? 'bg-amber-900/40 text-amber-300 border-amber-800'
                            : 'bg-green-900/40 text-green-300 border-green-800'
                        }`}>
                          {v.flag}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab: Distributions */}
          {tab === 'distributions' && (
            <div className="space-y-2">
              {report.distributions.map((d, i) => (
                <div key={i}
                  className="bg-gray-800 rounded-xl px-4 py-3 flex
                             items-center justify-between text-sm">
                  <span className="text-white font-mono w-40 truncate">
                    {d.column}
                  </span>
                  <div className="flex gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${
                      d.is_normal
                        ? 'bg-green-900/40 text-green-300 border-green-800'
                        : 'bg-purple-900/40 text-purple-300 border-purple-800'
                    }`}>
                      {d.is_normal ? 'normal' : 'non-normal'}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full border
                                     bg-gray-900 text-gray-400 border-gray-700">
                      {d.skew_type}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded-full border
                                     bg-gray-900 text-gray-400 border-gray-700">
                      {d.tail_type}
                    </span>
                    {d.recommended_transform !== 'none' && (
                      <span className="text-xs px-2 py-0.5 rounded-full border
                                       bg-teal-900/40 text-teal-300 border-teal-800">
                        suggest: {d.recommended_transform}
                      </span>
                    )}
                  </div>
                  <span className="text-gray-600 text-xs font-mono">
                    p={d.shapiro_p.toFixed(4)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Tab: Hypothesis tests */}
          {tab === 'hypothesis' && (
            <div className="space-y-3">
              {report.hypothesis_tests.length === 0 ? (
                <p className="text-gray-500 text-sm">
                  No categorical columns available for hypothesis testing.
                </p>
              ) : report.hypothesis_tests.map((h, i) => (
                <div key={i}
                  className={`rounded-xl border px-4 py-3 ${
                    h.significant
                      ? 'bg-teal-900/20 border-teal-800/50'
                      : 'bg-gray-800 border-gray-700'
                  }`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-mono px-2 py-0.5 rounded
                                      border ${
                      h.significant
                        ? 'text-teal-300 border-teal-800 bg-teal-900/40'
                        : 'text-gray-500 border-gray-700 bg-gray-900'
                    }`}>
                      {h.test}
                    </span>
                    <span className="text-gray-400 text-xs font-mono">
                      {h.columns.join(' × ')}
                    </span>
                    <span className={`ml-auto text-xs font-mono ${
                      h.significant ? 'text-teal-400' : 'text-gray-600'
                    }`}>
                      p={h.p_value.toFixed(4)}
                    </span>
                  </div>
                  <p className={`text-sm ${
                    h.significant ? 'text-teal-100' : 'text-gray-500'
                  }`}>
                    {h.interpretation}
                  </p>
                </div>
              ))}
            </div>
          )}

          {/* Tab: PCA */}
          {tab === 'pca' && (
            report.pca ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  {[
                    ['Total components', report.pca.n_components],
                    ['For 90% variance', report.pca.components_for_90pct],
                    ['PC1 explains', `${(report.pca.explained_variance[0] * 100).toFixed(1)}%`],
                  ].map(([label, val]) => (
                    <div key={label} className="bg-gray-800 rounded-xl p-3 text-center">
                      <p className="text-xl font-bold text-white">{val}</p>
                      <p className="text-gray-500 text-xs mt-1">{label}</p>
                    </div>
                  ))}
                </div>

                <div>
                  <p className="text-xs uppercase tracking-wide text-gray-500 mb-2">
                    Variance explained per component
                  </p>
                  <div className="space-y-1.5">
                    {report.pca.explained_variance.slice(0, 10).map((v, i) => (
                      <div key={i} className="flex items-center gap-3 text-xs">
                        <span className="text-gray-500 font-mono w-10">
                          PC{i + 1}
                        </span>
                        <div className="flex-1 h-2 bg-gray-800 rounded-full">
                          <div
                            className="h-full bg-purple-500 rounded-full"
                            style={{ width: `${v * 100}%` }}
                          />
                        </div>
                        <span className="text-gray-400 font-mono w-12 text-right">
                          {(v * 100).toFixed(1)}%
                        </span>
                        <span className="text-gray-600 font-mono w-16 text-right">
                          cum {(report.pca.cumulative_variance[i] * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-xs uppercase tracking-wide text-gray-500 mb-2">
                    Top contributing features per component
                  </p>
                  <div className="space-y-2">
                    {Object.entries(report.pca.top_features)
                      .slice(0, 5)
                      .map(([pc, features]) => (
                        <div key={pc}
                          className="flex items-center gap-3 text-sm bg-gray-800
                                     rounded-lg px-3 py-2">
                          <span className="text-purple-400 font-mono font-medium w-10">
                            {pc}
                          </span>
                          <div className="flex gap-2 flex-wrap">
                            {features.map(f => (
                              <span key={f}
                                className="text-xs font-mono text-gray-300
                                           bg-gray-900 px-2 py-1 rounded">
                                {f}
                              </span>
                            ))}
                          </div>
                        </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-gray-500 text-sm">
                PCA requires at least 3 numeric columns and 10 rows.
              </p>
            )
          )}
        </>
      )}
    </div>
  )
}