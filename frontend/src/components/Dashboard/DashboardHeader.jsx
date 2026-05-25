// frontend/src/components/Dashboard/DashboardHeader.jsx
export default function DashboardHeader({ dashboard }) {
  const gradeColor = {
    A: 'text-green-400',  B: 'text-teal-400',
    C: 'text-yellow-400', D: 'text-orange-400', F: 'text-red-400',
  }

  return (
    <div className="px-6 py-4 border-b border-gray-800
                    flex items-center gap-6 flex-wrap">
      <div>
        <p className="text-gray-500 text-xs uppercase tracking-wide">Dataset</p>
        <p className="text-white font-medium text-sm truncate max-w-[200px]">
          {dashboard.dataset_name}
        </p>
      </div>
      <div>
        <p className="text-gray-500 text-xs uppercase tracking-wide">Rows</p>
        <p className="text-white font-medium text-sm">
          {dashboard.row_count.toLocaleString()}
        </p>
      </div>
      <div>
        <p className="text-gray-500 text-xs uppercase tracking-wide">Columns</p>
        <p className="text-white font-medium text-sm">{dashboard.col_count}</p>
      </div>
      <div>
        <p className="text-gray-500 text-xs uppercase tracking-wide">Charts</p>
        <p className="text-white font-medium text-sm">{dashboard.charts.length}</p>
      </div>
      {dashboard.quality_score != null && (
        <div>
          <p className="text-gray-500 text-xs uppercase tracking-wide">
            Quality
          </p>
          <p className={`font-bold text-sm ${gradeColor[dashboard.quality_grade] || 'text-white'}`}>
            {dashboard.quality_score}/100
            <span className="ml-1 opacity-70">({dashboard.quality_grade})</span>
          </p>
        </div>
      )}
      <div className="ml-auto">
        <p className="text-gray-600 text-xs">
          Generated {new Date(dashboard.generated_at).toLocaleTimeString()}
        </p>
      </div>
    </div>
  )
}