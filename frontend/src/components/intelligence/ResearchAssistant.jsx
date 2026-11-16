import { useEffect, useState } from 'react';
import { ArrowUp, BookOpen, MessageSquare, Sparkles } from 'lucide-react';
import { api } from '../../api';
import { usePulse } from '../../context';
import { Badge, ErrorNotice, Loading, Panel } from '../ui/Primitives';

export default function ResearchAssistant({ analysis, onSource, suggestedQuestion }) {
  const { session } = usePulse();
  useEffect(() => {
    if (suggestedQuestion) setQuestion(suggestedQuestion.text);
  }, [suggestedQuestion]);
  const [question, setQuestion] = useState('');
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const ask = async (value) => {
    if (busy || value.trim().length < 3) return;
    setQuestion('');
    setBusy(true);
    setError('');
    try {
      const result = await api('/assistant', {
        method: 'POST',
        body: JSON.stringify({ analysis_id: analysis.id, question: value.trim() }),
      });
      setMessages((items) => [...items, { question: value.trim(), ...result }]);
    } catch (err) {
      setError(err.message);
      setQuestion(value);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div id="research-assistant">
      <Panel
        className="assistant-panel"
        title="Research assistant"
        description="Explore the reports and news behind this analysis."
        actions={<Sparkles size={19} />}
      >
        <div className="assistant-status">
          <span className="live-dot" />
          <span>
            {session.ai.available ? 'AI answers with source links' : 'Search company sources'}
          </span>
        </div>
        {!messages.length && (
          <div className="assistant-intro">
            <MessageSquare size={27} />
            <h3>What would you like to know?</h3>
            <p>
              {session.ai.available
                ? 'Ask a question and follow the source links to explore the answer.'
                : 'Ask a question to find relevant passages in the company’s reports and news.'}
            </p>
            <div className="suggested-questions">
              {[
                'Summarise the main findings.',
                'What environmental risks are mentioned?',
                'What evidence supports responsible AI?',
              ].map((q) => (
                <button disabled={busy} key={q} onClick={() => ask(q)}>
                  {q}
                  <ArrowUp size={13} />
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="assistant-messages" aria-live="polite">
          {messages.map((message, index) => (
            <article className="assistant-message" key={index}>
              <p className="asked-question">{message.question}</p>
              <Badge tone={message.mode === 'ai' ? 'green' : 'blue'}>
                {message.mode === 'ai' ? 'AI answer' : 'Source search'}
              </Badge>
              <p className="answer-text">{message.answer}</p>
              {message.citations.map((citation, i) => (
                <button
                  className="citation"
                  key={`${citation.source_id}-${i}`}
                  onClick={() => {
                    const source = [
                      ...analysis.sources,
                      ...(analysis.knowledge_sources || []),
                    ].find((s) => s.id === citation.source_id);
                    if (source) onSource(source);
                  }}
                >
                  <span>
                    <BookOpen size={14} />
                    {citation.page ? `Page ${citation.page}` : `Source ${i + 1}`}
                  </span>
                  <q>
                    {citation.quote.slice(0, 280)}
                    {citation.quote.length > 280 ? '…' : ''}
                  </q>
                  <small>{citation.title}</small>
                </button>
              ))}
              {message.notice && <p className="tiny muted">{message.notice}</p>}
            </article>
          ))}
        </div>
        {busy && <Loading>Finding relevant information…</Loading>}
        <ErrorNotice error={error} />
        <form
          className="assistant-input"
          onSubmit={(e) => {
            e.preventDefault();
            ask(question);
          }}
        >
          <label className="sr-only" htmlFor="assistant-question">
            Ask about this company research
          </label>
          <textarea
            id="assistant-question"
            value={question}
            maxLength={1200}
            onChange={(e) => setQuestion(e.target.value)}
            rows={2}
            placeholder="Ask about the company or its reports…"
          />
          <button
            className="icon-button"
            type="submit"
            disabled={busy || question.trim().length < 3}
            aria-label="Send question"
          >
            <ArrowUp size={19} />
          </button>
        </form>
        <p className="tiny muted">Always review the original sources before making a decision.</p>
      </Panel>
    </div>
  );
}
