import { BookOpen, ExternalLink } from 'lucide-react'
import { Link } from 'react-router-dom'
import { GLOSSARY_TERMS } from '../data/glossaryTerms'

export default function Glossary() {
    return (
        <div className="glossary-page">
            <div className="page-header">
                <h1>
                    <BookOpen size={32} />
                    Glossary
                </h1>
                <p className="page-description">
                    Quick definitions for recurring simulation and research terms.
                </p>
            </div>

            <div className="card">
                <div className="card-body glossary-intro">
                    <p>
                        These definitions are plain-language labels for viewer clarity.
                        They do not replace canonical protocol documents.
                    </p>
                    <div className="glossary-intro-links">
                        <Link to="/method" className="glossary-link">
                            Method & Technical Notes
                            <ExternalLink size={14} />
                        </Link>
                    </div>
                </div>
            </div>

            <div className="glossary-grid">
                {GLOSSARY_TERMS.map((term) => (
                    <article key={term.key} id={term.key} className="card glossary-card">
                        <div className="card-body">
                            <h3>{term.label}</h3>
                            <p>{term.definition}</p>
                        </div>
                    </article>
                ))}
            </div>

            <style>{`
        .glossary-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: var(--spacing-md);
        }

        .glossary-intro {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: var(--spacing-md);
          flex-wrap: wrap;
        }

        .glossary-intro p {
          color: var(--text-secondary);
          margin: 0;
        }

        .glossary-link {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          color: var(--text-primary);
          font-size: 0.875rem;
          font-weight: 600;
        }

        .glossary-link:hover {
          text-decoration: underline;
        }

        .glossary-card h3 {
          margin-bottom: var(--spacing-sm);
          color: var(--text-primary);
        }

        .glossary-card p {
          margin: 0;
          color: var(--text-secondary);
          line-height: 1.6;
        }
      `}</style>
        </div>
    )
}
