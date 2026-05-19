export default function PreviewTable({ columns, rows }) {
  const colNames = columns.map((c) => c.name)

  return (
    <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
      <h3 className="text-sm font-medium text-gray-400 mb-4">
        Data preview — first 10 rows
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800">
              {colNames.map((name) => (
                <th
                  key={name}
                  className="text-left text-gray-500 font-medium pb-2 pr-6 whitespace-nowrap"
                >
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={i}
                className="border-b border-gray-800/50 hover:bg-gray-800/40"
              >
                {colNames.map((name) => (
                  <td
                    key={name}
                    className="py-2 pr-6 text-gray-300 whitespace-nowrap"
                  >
                    {row[name] === null || row[name] === undefined
                      ? <span className="text-red-400/60 italic text-xs">null</span>
                      : String(row[name])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}