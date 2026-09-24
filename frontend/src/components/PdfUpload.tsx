import { useState } from 'react';
import './PdfUpload.css';

export default function PdfUpload({ onSuccess }: { onSuccess?: () => void }) {
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [deckName, setDeckName] = useState('');
  const [error, setError] = useState('');

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFile(files[0]);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.currentTarget.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
    // Reset so selecting the same file again still fires onChange
    e.currentTarget.value = '';
  };

  const handleFile = async (file: File) => {
    if (!file.name.endsWith('.pdf')) {
      setError('Please upload a PDF file');
      return;
    }

    if (file.size > 50 * 1024 * 1024) {
      setError('File is too large (max 50MB)');
      return;
    }

    const trimmedDeckName = deckName.trim();
    if (!trimmedDeckName) {
      setError('Please enter a deck name');
      return;
    }

    setIsLoading(true);
    setError('');

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('deckName', trimmedDeckName);
      formData.append('userId', 'user1');

      const response = await fetch('http://localhost:8000/api/ingest', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        setError(data.detail || data.message || 'Upload failed');
        return;
      }

      setDeckName('');
      setTimeout(() => onSuccess?.(), 600);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
      console.error('Upload error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="pdf-upload-container">
      <div
        className={`upload-area ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="upload-content">
          <p className="upload-title">Upload lecture notes or slides</p>
          <p className="upload-subtitle">
            Drag and drop a PDF, or click to browse
          </p>
        </div>

        <input
          type="file"
          accept=".pdf"
          onChange={handleFileInput}
          style={{ display: 'none' }}
          id="file-input"
          disabled={isLoading}
        />
        <label
          htmlFor="file-input"
          className="upload-button"
          style={{ cursor: isLoading ? 'not-allowed' : 'pointer' }}
        >
          {isLoading ? 'Processing...' : 'Choose file'}
        </label>
      </div>

      <div className="form-section">
        <input
          type="text"
          placeholder="Deck name (e.g., 'Organic Chemistry - Chapter 3')"
          value={deckName}
          onChange={(e) => setDeckName(e.target.value)}
          disabled={isLoading}
          className="deck-name-input"
        />

        {isLoading && (
          <div className="progress-section">
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `100%` }}
              />
            </div>
            <p className="progress-text">
              ⏳ Processing your PDF... This may take several minutes depending on file size and your hardware. Check the backend terminal for progress.
            </p>
          </div>
        )}

        {error && <p className="error-message">{error}</p>}
      </div>
    </div>
  );
}
