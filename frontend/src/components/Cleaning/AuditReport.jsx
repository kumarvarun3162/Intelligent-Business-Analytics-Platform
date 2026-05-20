const STAGE_COLORS = {
  type_inference:       'bg-blue-900/40 text-blue-300 border-blue-800',
  missing_values:       'bg-amber-900/40 text-amber-300 border-amber-800',
  duplicates:           'bg-purple-900/40 text-purple-300 border-purple-800',
  outliers:             'bg-red-900/40 text-red-300 border-red-800',
  string_normalization: 'bg-teal-900/40 text-teal-300 border-teal-800',
  constant_removal:     'bg-gray-800 text-gray-400 border-gray-700',
  column_names:         'bg-indigo-900/40 text-indigo-300 border-indigo-800',
}

export default function AuditReport({ actions }) {
  if (!actions?.length) return null

  // Group actions by stage
  const grouped = actions.reduce((acc, a) => {
    if (!acc[a.stage]) acc[a.stage] = []
    acc[a.stage].push(a)
    return acc
  }, {})

  return (
    <div>
      <h3 className="text-sm font-medium text-gray-400 mb-3">
        Cleaning audit trail — {actions.length} actions taken
      </h3>
      <div className="space-y-3">
        {Object.entries(grouped).map(([stage, stageActions]) => (
          <div
            key={stage}
            className={`rounded-xl border p-4 ${STAGE_COLORS[stage] || 'bg-gray-800 text-gray-400 border-gray-700'}`}
          >
            <p className="font-medium text-sm mb-2 capitalize">
              {stage.replace(/_/g, ' ')}
              <span className="ml-2 opacity-60 font-normal">
                ({stageActions.length} action{stageActions.length > 1 ? 's' : ''})
              </span>
            </p>
            <ul className="space-y-1">
              {stageActions.map((a, i) => (
                <li key={i} className="text-xs opacity-80 flex items-start gap-2">
                  <span className="mt-0.5 opacity-50">→</span>
                  <span>
                    {a.column && (
                      <span className="font-mono opacity-70">[{a.column}] </span>
                    )}
                    {a.detail}
                    {a.rows_affected > 0 && (
                      <span className="opacity-50"> · {a.rows_affected} rows</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}