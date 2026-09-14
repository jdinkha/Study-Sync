import { useState, useEffect } from 'react';
import PdfUpload from './components/PdfUpload';
import DeckList from './pages/DeckList';
import StudySession from './pages/StudySession';
import './App.css';

type View =
  | { name: 'decks' }
  | { name: 'upload' }
  | { name: 'study'; deckId: string; deckName: string };

export default function App() {
  const [view, setView] = useState<View>({ name: 'decks' });
  const [refreshKey, setRefreshKey] = useState(0);
  const [models, setModels] = useState<string[]>([]);
  const [activeModel, setActiveModel] = useState('');

  useEffect(() => {
    fetchModels();
  }, []);

  async function fetchModels() {
    try {
      const res = await fetch('http://localhost:8000/api/models');
      const data = await res.json();
      setModels(data.models);
      setActiveModel(data.active);
    } catch {
      // Ollama not running — silently ignore, backend will catch it on upload
    }
  }

  async function handleModelChange(model: string) {
    setActiveModel(model);
    try {
      await fetch(`http://localhost:8000/api/config/model?model=${encodeURIComponent(model)}`, {
        method: 'POST',
      });
    } catch {
      console.error('Failed to switch model');
    }
  }

  function goToDecks() {
    if (view.name !== 'decks') {
      setRefreshKey(k => k + 1);
    }
    setView({ name: 'decks' });
  }

  return (
    <div className="app">
      {view.name !== 'study' && (
        <header className="app-header">
          <div className="app-header-inner">
            <h1 className="app-title" onClick={goToDecks}>StudySync AI</h1>

            <div className="app-header-controls">
              <nav className="app-nav">
                <button
                  className={`app-nav-btn ${view.name === 'decks' ? 'active' : ''}`}
                  onClick={() => setView({ name: 'decks' })}
                >
                  My Decks
                </button>
                <button
                  className={`app-nav-btn ${view.name === 'upload' ? 'active' : ''}`}
                  onClick={() => setView({ name: 'upload' })}
                >
                  + Upload PDF
                </button>
              </nav>

              {models.length > 0 && (
                <div className="app-model-selector">
                  <label className="app-model-label" htmlFor="model-select">
                    Model
                  </label>
                  <select
                    id="model-select"
                    className="app-model-select"
                    value={activeModel}
                    onChange={e => handleModelChange(e.target.value)}
                  >
                    {models.map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>

          </div>
        </header>
      )}

      <main className="app-main">
        {view.name === 'decks' && (
          <DeckList
            key={refreshKey}
            onStudy={(deckId, deckName) =>
              setView({ name: 'study', deckId, deckName })
            }
          />
        )}
        {view.name === 'upload' && (
          <PdfUpload onSuccess={goToDecks} />
        )}
        {view.name === 'study' && (
          <StudySession
            deckId={view.deckId}
            deckName={view.deckName}
            onBack={goToDecks}
          />
        )}
      </main>
    </div>
  );
}
