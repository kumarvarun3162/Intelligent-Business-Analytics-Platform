import { useState, useRef } from 'react'
import axios from 'axios'
import API_BASE from '../../api/config'

export default function UploadZone({ onResult }) {
  const [dragging, setDragging]   = useState(false)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [progress, setProgress]   = useState(0)
  const inputRef = useRef()

  const handleFile = async (file) => {
    if (!file) return
    setError(null)
    setLoading(true)
    setProgress(0)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await axios.post(`${API_BASE}/api/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          setProgress(Math.round((e.loaded / e.total) * 100))
        },
      })
      onResult(res.data)
    } catch (err) {
      const msg = err.response?.data?.detail || 'Upload failed. Please try again.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        handleFile(e.dataTransfer.files[0])
      }}
      onClick={() => inputRef.current?.click()}
      className={`
        border-2 border-dashed rounded-2xl p-16
        flex flex-col items-center justify-center gap-4
        cursor-pointer transition-all duration-200
        ${dragging
          ? 'border-blue-400 bg-blue-950/30'
          : 'border-gray-700 hover:border-gray-500 bg-gray-900'}
      `}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.xlsx,.xls,.json"
        className="hidden"
        onChange={(e) => handleFile(e.target.files[0])}
      />

      {loading ? (
        <div className="text-center space-y-3">
          <div className="w-48 h-2 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-gray-400 text-sm">Analyzing your data... {progress}%</p>
        </div>
      ) : (
        <>
          <div className="text-5xl">📂</div>
          <div className="text-center">
            <p className="text-gray-200 font-medium">
              Drop your file here or click to browse
            </p>
            <p className="text-gray-500 text-sm mt-1">
              CSV · Excel · JSON — up to 50 MB
            </p>
          </div>
        </>
      )}

      {error && (
        <p className="text-red-400 text-sm mt-2 text-center">{error}</p>
      )}
    </div>
  )
}