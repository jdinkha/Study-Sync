import { useState, useEffect } from 'react';
import './StudySession.css';

interface Card {
  id: string;
  front: string;
  back: string;
  choices: string[];
  ef: number;
  interval: number;
  reps: number;
}

const RATINGS = [
  { q: 0, label: 'Blackout',  color: '#c0392b', hint: 'Complete blank' },
  { q: 1, label: 'Wrong',     color: '#e74c3c', hint: 'Incorrect' },
  { q: 2, label: 'Hard',      color: '#e67e22', hint: 'Correct but tough' },
  { q: 3, label: 'Okay',      color: '#f39c12', hint: 'Correct with effort' },
  { q: 4, label: 'Good',      color: '#27ae60', hint: 'Correct, hesitated' },
  { q: 5, label: 'Easy',      color: '#2ecc71', hint: 'Instant recall' },
];

export default function StudySession({ deckId, deckName, onBack }: {
  deckId: string;
  deckName: string;
  onBack: () => void;
}) {
  const [cards, setCards] = useState<Card[]>([]);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [selectedChoice, setSelectedChoice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [reviewed, setReviewed] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchDueCards();
  }, [deckId]);

  async function fetchDueCards() {
    setLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/cards/due?deckId=${deckId}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load cards');
      setCards(data);
      if (data.length === 0) setDone(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load cards');
    } finally {
      setLoading(false);
    }
  }

  async function submitRating(quality: number) {
    if (submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch('http://localhost:8000/api/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cardId: cards[index].id, quality }),
      });
      if (!res.ok) throw new Error('Failed to submit review');

      setReviewed(r => r + 1);
      setFlipped(false);
      setSelectedChoice(null);

      // Brief pause so the flip-back animates before advancing
      setTimeout(() => {
        if (index + 1 >= cards.length) {
          setDone(true);
        } else {
          setIndex(i => i + 1);
        }
      }, 250);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit');
    } finally {
      setSubmitting(false);
    }
  }

  // ── Loading ──────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="ss-center">
        <p className="ss-loading">Loading cards...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="ss-center">
        <p className="ss-error">{error}</p>
        <button className="ss-btn-outline" onClick={onBack}>Go back</button>
      </div>
    );
  }

  // ── Done screen ───────────────────────────────────────────────────────────────
  if (done) {
    return (
      <div className="ss-center">
        <div className="ss-done">
          <div className="ss-done-icon">✓</div>
          <h2 className="ss-done-title">Session complete</h2>
          <p className="ss-done-sub">
            You reviewed <strong>{reviewed}</strong> card{reviewed !== 1 ? 's' : ''} from <strong>{deckName}</strong>.
          </p>
          {cards.length === 0 && reviewed === 0 && (
            <p className="ss-done-note">No cards are due right now. Come back tomorrow!</p>
          )}
          <button className="ss-btn-primary" onClick={onBack}>Back to decks</button>
        </div>
      </div>
    );
  }

  const card = cards[index];
  const progress = ((index) / cards.length) * 100;
  const hasChoices = card.choices && card.choices.length > 0;
  const isCorrect = selectedChoice !== null &&
    selectedChoice.trim().toLowerCase() === card.back.trim().toLowerCase();

  function handleChoice(choice: string) {
    if (flipped) return;
    setSelectedChoice(choice);
    setFlipped(true);
  }

  // ── Study UI ──────────────────────────────────────────────────────────────────
  return (
    <div className="ss-container">

      {/* Header */}
      <div className="ss-header">
        <button className="ss-back" onClick={onBack}>← Back</button>
        <span className="ss-deck-name">Current Deck: {deckName}</span>
        <span className="ss-counter">{index + 1} / {cards.length}</span>
      </div>

      {/* Progress bar */}
      <div className="ss-progress-bar">
        <div className="ss-progress-fill" style={{ width: `${progress}%` }} />
      </div>

      {/* Card */}
      <div className="ss-card-wrap">
        <div className={`ss-card ${flipped ? 'flipped' : ''}`}>
          {/* Front */}
          <div className="ss-card-front">
            <span className="ss-card-label">Question</span>
            <p className="ss-card-text">{card.front}</p>
            {hasChoices ? (
              <div className="ss-choices">
                {card.choices.map((choice, i) => (
                  <button
                    key={i}
                    className="ss-choice-btn"
                    onClick={() => handleChoice(choice)}
                  >
                    {choice}
                  </button>
                ))}
              </div>
            ) : (
              <button className="ss-reveal-btn" onClick={() => setFlipped(true)}>
                Tap to reveal answer
              </button>
            )}
          </div>

          {/* Back */}
          <div className="ss-card-back">
            <span className="ss-card-label">
              {hasChoices ? (isCorrect ? 'Correct!' : 'Not quite') : 'Answer'}
            </span>
            <p className="ss-card-text">{card.back}</p>
            {hasChoices && !isCorrect && selectedChoice && (
              <p className="ss-your-answer">You chose: {selectedChoice}</p>
            )}
          </div>
        </div>
      </div>

      {/* Rating buttons — only shown after flip */}
      <div className={`ss-ratings ${flipped ? 'visible' : ''}`}>
        <p className="ss-ratings-label">How well did you know this?</p>
        <div className="ss-ratings-row">
          {RATINGS.map(({ q, label, color, hint }) => (
            <button
              key={q}
              className="ss-rating-btn"
              style={{ '--rating-color': color } as React.CSSProperties}
              onClick={() => submitRating(q)}
              disabled={submitting}
              title={hint}
            >
              <span className="ss-rating-num">{q}</span>
              <span className="ss-rating-label">{label}</span>
            </button>
          ))}
        </div>
      </div>


    </div>
  );
}
