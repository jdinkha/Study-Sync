import { useState, useEffect } from 'react';
import './DeckList.css';

interface Deck {
  id: string;
  name: string;
  createdAt: string;
  cardCount: number;
}

export default function DeckList({ onStudy }: {
  onStudy: (deckId: string, deckName: string) => void;
}) {
  const [decks, setDecks] = useState<Deck[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchDecks();
  }, []);

  async function fetchDecks() {
    try {
      const res = await fetch('http://localhost:8000/api/decks?userId=user1');
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load decks');
      setDecks(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load decks');
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <p className="dl-state">Loading decks...</p>;
  if (error)   return <p className="dl-state dl-error">{error}</p>;

  if (decks.length === 0) {
    return (
      <div className="dl-empty">
        <p className="dl-empty-title">No decks yet</p>
        <p className="dl-empty-sub">Upload a PDF to create your first deck.</p>
      </div>
    );
  }

  return (
    <div className="dl-list">
      {decks.map(deck => (
        <div key={deck.id} className="dl-card">
          <div className="dl-card-info">
            <p className="dl-card-name">{deck.name}</p>
            <p className="dl-card-meta">
              {deck.cardCount} cards · Created {new Date(deck.createdAt).toLocaleDateString()}
            </p>
          </div>
          <button
            className="dl-study-btn"
            onClick={() => onStudy(deck.id, deck.name)}
          >
            Study →
          </button>
        </div>
      ))}
    </div>
  );
}
