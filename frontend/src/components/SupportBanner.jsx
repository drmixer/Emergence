import { Heart, ExternalLink } from 'lucide-react'
import { useState } from 'react'

export default function SupportBanner() {
    const [dismissed, setDismissed] = useState(false)

    // Check localStorage to not show again if dismissed
    const isDismissed = dismissed || localStorage.getItem('support-banner-dismissed')

    if (isDismissed) return null

    const handleDismiss = () => {
        setDismissed(true)
        localStorage.setItem('support-banner-dismissed', 'true')
    }

    return (
        <div className="support-banner">
            <div className="support-content">
                <Heart size={16} className="support-icon" />
                <span>
                    This experiment costs ~$30/month to run.
                    If you find it valuable, you can{' '}
                    <a
                        href="https://github.com/sponsors/your-username"
                        target="_blank"
                        rel="noopener noreferrer"
                    >
                        help cover compute costs
                        <ExternalLink size={12} />
                    </a>
                </span>
            </div>
            <button
                className="support-dismiss"
                onClick={handleDismiss}
                aria-label="Dismiss"
            >
                ×
            </button>

            <style>{`
        .support-banner {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: var(--spacing-sm) var(--spacing-md);
          background: rgba(139, 92, 246, 0.1);
          border-bottom: 1px solid rgba(139, 92, 246, 0.2);
          font-size: 0.8125rem;
          color: var(--text-secondary);
        }
        
        .support-content {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
        }
        
        .support-icon {
          color: #ec4899;
          flex-shrink: 0;
        }
        
        .support-banner a {
          color: var(--accent-purple);
          display: inline-flex;
          align-items: center;
          gap: 4px;
        }
        
        .support-banner a:hover {
          text-decoration: underline;
        }
        
        .support-dismiss {
          background: none;
          border: none;
          color: var(--text-muted);
          font-size: 1.25rem;
          cursor: pointer;
          padding: 0 var(--spacing-sm);
          line-height: 1;
        }
        
        .support-dismiss:hover {
          color: var(--text-primary);
        }
      `}</style>
        </div>
    )
}
