import { useState } from 'react'
import UploadZone from './components/Upload/UploadZone'
import PreviewTable from './components/Upload/PreviewTable'
import MetadataCard from './components/Upload/MetadataCard'

export default function App() {
  const [result, setResult] = useState(null)

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 p-8">
      <header className="max-w-5xl mx-auto mb-10">
        <h1 className="text-3xl font-bold text-white tracking-tight">
          IBAP
        </h1>
        <p className="text-gray-400 mt-1">
          Intelligent Business Analytics Platform
        </p>
      </header>

      <main className="max-w-5xl mx-auto space-y-8">
        <UploadZone onResult={setResult} />
        {result && (
          <>
            <MetadataCard metadata={result.metadata} />
            <PreviewTable
              columns={result.metadata.columns}
              rows={result.preview}
            />
          </>
        )}
      </main>
    </div>
  )
}