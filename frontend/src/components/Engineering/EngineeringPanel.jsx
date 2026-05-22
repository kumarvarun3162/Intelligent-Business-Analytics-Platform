// frontend/src/components/Engineering/EngineeringPanel.jsx
import { useState } from 'react'
import axios from 'axios'

const API_BASE = 'http://localhost:8080'

const TRANSFORM_COLORS = {
  one_hot_encode:     'bg-purple-900/40 text-purple-300 border-purple-800',
  label_encode:       'bg-blue-900/40 text-blue-300 border-blue-800',
  frequency_encode:   'bg-indigo-900/40 text-indigo-300 border-indigo-800',
  bool_to_int:        'bg-gray-800 text-gray-400 border-gray-700',
  minmax_scale:       'bg-teal-900/40 text-teal-300 border-teal-800',
  standard_scale:     'bg-cyan-900/40 text-cyan-300 border-cyan-800',
  robust_scale:       'bg-emerald-900/40 text-emerald-300 border-emerald-800',
  datetime_extract:   'bg-amber-900/40 text-amber-300 border-amber-800',
  bin_quantile:       'bg-orange-900/40 text-orange-300 border-orange-800',
  bin_uniform:        'bg-yellow-900/40 text-yellow-300 border-yellow-800',
  log_transform:      'bg-pink-900/40 text-pink-300 border-pink-800',
  ratio_feature:      'bg-rose-900/40 text-rose-300 border-rose-800',
  polynomial_feature: 'bg-red-900/40 text-red-300 border-red-800',
}

export default function EngineeringPanel({ sessionId, onEngineered }) {
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState(null)
  const [error, setError]     = useState(null)
  const [options, setOptions] = useState({
    scale_method:  'auto',
    n_bins:        5,
    bin_strategy:  'quantile',
    drop_datetime: false,
  })

  const handleEngineer = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await axios.post(`${API_BASE}/api/engineer`, {
        session_id: sessionId,
        ...options,
      })
      setResult(res.data)
      onEngineered?.(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Engineering failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">Feature engineering</h2>
        <p className="text-gray-500 text-sm mt-1">
          Encode, scale, extract, and derive features for ML readiness
        </p>
      </div>

      {/* Options grid */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wide block mb-1">
            Scaling method
          </label>
          <select
            value={options.scale_method}
            onChange={e => setOptions(o => ({ ...o, scale_method: e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                       text-gray-200 text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="auto">Auto (recommended)</option>
            <option value="minmax">Min-max [0,1]</option>
            <option value="standard">Standard (Z-score)</option>
            <option value="robust">Robust (IQR)</option>
            <option value="none">None — skip scaling</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wide block mb-1">
            Binning strategy
          </label>
          <select
            value={options.bin_strategy}
            onChange={e => setOptions(o => ({ ...o, bin_strategy: e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                       text-gray-200 text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="quantile">Quantile (equal frequency)</option>
            <option value="uniform">Uniform (equal width)</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wide block mb-1">
            Number of bins
          </label>
          <select
            value={options.n_bins}
            onChange={e => setOptions(o => ({ ...o, n_bins: parseInt(e.target.value) }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                       text-gray-200 text-sm focus:outline-none focus:border-blue-500"
          >
            {[3, 4, 5, 6, 8, 10].map(n => (
              <option key={n} value={n}>{n} bins</option>
            ))}
          </select>
        </div>

        <div className="flex items-end pb-1">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={options.drop_datetime}
              onChange={e => setOptions(o => ({ ...o, drop_datetime: e.target.checked }))}
              className="w-4 h-4 rounded accent-blue-500"
            />
            <span className="text-sm text-gray-300">
              Drop original datetime columns
            </span>
          </label>
        </div>
      </div>

      <button
        onClick={handleEngineer}
        disabled={loading}
        className="w-full bg-purple-700 hover:bg-purple-600 disabled:bg-gray-700
                   text-white font-medium py-3 rounded-xl transition-colors"
      >
        {loading ? 'Engineering features…' : 'Run engineering pipeline'}
      </button>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Summary hero */}
      {result?.report && (
        <>
          <div className="bg-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-gray-400 text-sm">ML readiness</p>
                <p className={`text-2xl font-bold mt-1 ${
                  result.report.ml_ready ? 'text-green-400' : 'text-amber-400'
                }`}>
                  {result.report.ml_ready ? 'Ready' : 'Needs review'}
                </p>
              </div>
              <div className="text-right">
                <p className="text-gray-400 text-sm">Columns</p>
                <p className="text-white font-bold text-xl">
                  {result.report.original_col_count}
                  <span className="text-gray-500 font-normal text-sm mx-1">→</span>
                  {result.report.engineered_col_count}
                  <span className="text-green-400 text-sm ml-1">
                    +{result.report.new_cols_created}
                  </span>
                </p>
              </div>
            </div>

            {/* Validation badges */}
            <div className="flex flex-wrap gap-2 mb-4">
              {result.report.validation_results
                .filter(v => v.column === '__dataset__')
                .map((v, i) => (
                  <span
                    key={i}
                    className={`text-xs px-2 py-1 rounded-full border ${
                      v.passed
                        ? 'bg-green-900/40 text-green-300 border-green-800'
                        : 'bg-red-900/40 text-red-300 border-red-800'
                    }`}
                  >
                    {v.passed ? '✓' : '✗'} {v.rule.replace(/_/g, ' ')}
                  </span>
                ))
              }
            </div>

            {/* Transform summary pills */}
            <p className="text-xs text-gray-500 mb-2 uppercase tracking-wide">
              Transforms applied — {result.report.transforms.length} total
            </p>
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {result.report.transforms.map((t, i) => (
                <div
                  key={i}
                  className={`rounded-lg border px-3 py-2 text-xs
                    ${TRANSFORM_COLORS[t.transform] || 'bg-gray-800 text-gray-400 border-gray-700'}`}
                >
                  <span className="font-mono font-medium">{t.transform}</span>
                  <span className="opacity-60 mx-1">·</span>
                  <span className="font-mono opacity-70">{t.column}</span>
                  <span className="opacity-50 mx-1">→</span>
                  <span className="opacity-80">{t.note}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}