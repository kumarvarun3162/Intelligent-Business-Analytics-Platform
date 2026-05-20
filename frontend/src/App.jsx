// frontend/src/App.jsx
import { useState } from 'react'
import UploadZone from './components/Upload/UploadZone'
import PreviewTable from './components/Upload/PreviewTable'
import MetadataCard from './components/Upload/MetadataCard'
import CleaningPanel from './components/Cleaning/CleaningPanel'

export default function App() {
  const [uploadResult, setUploadResult] = useState(null)
  const [cleanResult, setCleanResult]   = useState(null)

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <header className="max-w-5xl mx-auto mb-10">
        <h1 className="text-3xl font-bold text-white tracking-tight">IBAP</h1>
        <p className="text-gray-400 mt-1">Intelligent Business Analytics Platform</p>
      </header>

      <main className="max-w-5xl mx-auto space-y-8">
        <UploadZone onResult={setUploadResult} />

        {uploadResult && (
          <>
            <MetadataCard metadata={uploadResult.metadata} />
            <PreviewTable
              columns={uploadResult.metadata.columns}
              rows={uploadResult.preview}
            />
            <CleaningPanel
              sessionId={uploadResult.metadata.session_id}
              onCleaned={setCleanResult}
            />
          </>
        )}

        {cleanResult && (
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
            <h3 className="text-sm font-medium text-gray-400 mb-4">
              Cleaned data preview
            </h3>
            <PreviewTable
              columns={cleanResult.report.column_type_map
                ? Object.entries(cleanResult.report.column_type_map).map(([name, dtype]) => ({
                    name, dtype, null_count: 0, null_percentage: 0, unique_count: 0, sample_values: []
                  }))
                : []}
              rows={cleanResult.preview}
            />
          </div>
        )}
      </main>
    </div>
  )
}