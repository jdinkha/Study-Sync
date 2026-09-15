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
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDeck, setConfirmDeck] = useState<Deck | null>(null);

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

  async function confirmDelete() {
    if (!confirmDeck) return;
    const deck = confirmDeck;
    setConfirmDeck(null);
    setDeletingId(deck.id);
    try {
      const res = await fetch(`http://localhost:8000/api/decks/${deck.id}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to delete deck');
      }
      setDecks(ds => ds.filter(d => d.id !== deck.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete deck');
    } finally {
      setDeletingId(null);
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
          <div className="dl-card-actions">
            <button
              className="dl-delete-btn"
              onClick={() => setConfirmDeck(deck)}
              disabled={deletingId === deck.id}
              title="Delete deck"
            >
              {deletingId === deck.id ? 'Deleting...' : 'Delete'}
            </button>
            <button
              className="dl-study-btn"
              onClick={() => onStudy(deck.id, deck.name)}
            >
              Study →
            </button>
          </div>
        </div>
      ))}

      {confirmDeck && (
        <div className="dl-modal-overlay" onClick={() => setConfirmDeck(null)}>
          <div className="dl-modal" onClick={e => e.stopPropagation()}>
            <p className="dl-modal-title">Delete deck</p>
            <p className="dl-modal-text">
              Are you sure you want to delete the deck "<strong>{confirmDeck.name}</strong>"?
            </p>
            <div className="dl-modal-actions">
              <button className="dl-modal-cancel" onClick={() => setConfirmDeck(null)}>
                Cancel
              </button>
              <button className="dl-modal-confirm" onClick={confirmDelete}>
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
