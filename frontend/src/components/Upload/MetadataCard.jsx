export default function MetadataCard({ metadata }) {
  const stats = [
    { label: 'Rows',       value: metadata.row_count.toLocaleString() },
    { label: 'Columns',    value: metadata.column_count },
    { label: 'File size',  value: `${metadata.file_size_kb} KB` },
    { label: 'Encoding',   value: metadata.encoding.toUpperCase() },
    { label: 'File type',  value: metadata.file_type.toUpperCase() },
    { label: 'Session ID', value: metadata.session_id.slice(0, 8) + '…' },
  ]

  return (
    <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
      <h2 className="text-lg font-semibold text-white mb-1">
        {metadata.original_name}
      </h2>
      <p className="text-green-400 text-sm mb-5">
        ✓ File parsed successfully
      </p>

      <div className="grid grid-cols-3 gap-4 mb-6">
        {stats.map((s) => (
          <div key={s.label} className="bg-gray-800 rounded-xl p-4">
            <p className="text-gray-500 text-xs uppercase tracking-wide">
              {s.label}
            </p>
            <p className="text-white font-semibold mt-1">{s.value}</p>
          </div>
        ))}
      </div>

      <h3 className="text-sm font-medium text-gray-400 mb-3">
        Column overview
      </h3>
      <div className="space-y-2">
        {metadata.columns.map((col) => (
          <div
            key={col.name}
            className="flex items-center gap-3 bg-gray-800 rounded-lg px-4 py-2 text-sm"
          >
            <span className="text-white font-medium w-40 truncate">
              {col.name}
            </span>
            <span className="text-blue-400 text-xs font-mono w-20">
              {col.dtype}
            </span>
            <span className="text-gray-400 text-xs">
              {col.null_count > 0
                ? <span className="text-amber-400">
                    {col.null_percentage}% nulls
                  </span>
                : <span className="text-green-400">no nulls</span>
              }
            </span>
            <span className="text-gray-500 text-xs ml-auto">
              {col.unique_count} unique
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}