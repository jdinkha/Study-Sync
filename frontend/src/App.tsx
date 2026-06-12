import { useState } from 'react';
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

  function goToDecks() {
    if (view.name !== 'decks') {
      setRefreshKey(k => k + 1); // force DeckList to re-fetch if not already on decks
    }
    setView({ name: 'decks' });
  }

  return (
    <div className="app">
      {/* Only show header when not in a study session */}
      {view.name !== 'study' && (
        <header className="app-header">
          <div className="app-header-inner">
            <h1 className="app-title" onClick={goToDecks}>StudySync AI</h1>
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
                Upload PDF
              </button>
            </nav>
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
