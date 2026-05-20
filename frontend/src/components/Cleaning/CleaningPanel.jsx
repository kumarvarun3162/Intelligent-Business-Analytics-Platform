import { useState } from 'react'
import axios from 'axios'
import AuditReport from './AuditReport'

const API_BASE = 'http://localhost:8080'

const GRADE_COLOR = {
  A: 'text-green-400',
  B: 'text-teal-400',
  C: 'text-yellow-400',
  D: 'text-orange-400',
  F: 'text-red-400',
}

export default function CleaningPanel({ sessionId, onCleaned }) {
  const [loading, setLoading]   = useState(false)
  const [result, setResult]     = useState(null)
  const [error, setError]       = useState(null)
  const [options, setOptions]   = useState({
    outlier_method:      'iqr',
    outlier_action:      'cap',
    null_drop_threshold: 0.5,
  })

  const handleClean = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await axios.post(`${API_BASE}/api/clean`, {
        session_id: sessionId,
        ...options,
      })
      setResult(res.data)
      onCleaned?.(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Cleaning failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">Data cleaning engine</h2>
        <p className="text-gray-500 text-sm mt-1">
          Configure and run the automated 8-stage cleaning pipeline
        </p>
      </div>

      {/* Options */}
      <div className="grid grid-cols-3 gap-4">
        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wide block mb-1">
            Outlier method
          </label>
          <select
            value={options.outlier_method}
            onChange={e => setOptions(o => ({ ...o, outlier_method: e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                       text-gray-200 text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="iqr">IQR (recommended)</option>
            <option value="zscore">Z-score (normal data)</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wide block mb-1">
            Outlier action
          </label>
          <select
            value={options.outlier_action}
            onChange={e => setOptions(o => ({ ...o, outlier_action: e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                       text-gray-200 text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="cap">Cap (Winsorize)</option>
            <option value="flag">Flag (add column)</option>
            <option value="drop">Drop rows</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-gray-500 uppercase tracking-wide block mb-1">
            Null drop threshold
          </label>
          <select
            value={options.null_drop_threshold}
            onChange={e => setOptions(o => ({
              ...o, null_drop_threshold: parseFloat(e.target.value)
            }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                       text-gray-200 text-sm focus:outline-none focus:border-blue-500"
          >
            <option value={0.3}>30% (aggressive)</option>
            <option value={0.5}>50% (default)</option>
            <option value={0.7}>70% (lenient)</option>
          </select>
        </div>
      </div>

      <button
        onClick={handleClean}
        disabled={loading}
        className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700
                   text-white font-medium py-3 rounded-xl transition-colors"
      >
        {loading ? 'Cleaning your data…' : 'Run cleaning pipeline'}
      </button>

      {error && (
        <p className="text-red-400 text-sm">{error}</p>
      )}

      {/* Quality score hero */}
      {result?.report && (
        <div className="bg-gray-800 rounded-xl p-5 flex items-center justify-between">
          <div>
            <p className="text-gray-400 text-sm">Data quality score</p>
            <p className={`text-5xl font-bold mt-1 ${GRADE_COLOR[result.report.quality_grade]}`}>
              {result.report.quality_score}
              <span className="text-2xl text-gray-500">/100</span>
            </p>
            <p className={`text-lg font-semibold mt-1 ${GRADE_COLOR[result.report.quality_grade]}`}>
              Grade {result.report.quality_grade}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-right">
            {[
              ['Rows removed',   result.report.rows_removed],
              ['Cols removed',   result.report.cols_removed],
              ['Nulls filled',   result.report.total_nulls_before - result.report.total_nulls_after],
              ['Outliers fixed', result.report.outliers_detected],
              ['Dupes removed',  result.report.duplicates_removed],
              ['Final rows',     result.report.cleaned_row_count],
            ].map(([label, val]) => (
              <div key={label} className="bg-gray-900 rounded-lg p-3">
                <p className="text-gray-500 text-xs">{label}</p>
                <p className="text-white font-semibold">{val.toLocaleString()}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {result?.report && <AuditReport actions={result.report.actions} />}
    </div>
  )
}