import { Heart, Github, Twitter, ExternalLink } from 'lucide-react'

export default function Footer() {
    return (
        <footer className="site-footer">
            <div className="footer-content">
                <div className="footer-section">
                    <div className="footer-logo">
                        <div className="logo-icon-small">E</div>
                        <span>Emergence</span>
                    </div>
                    <p className="footer-tagline">
                        An experiment in AI civilization
                    </p>
                </div>

                <div className="footer-section">
                    <h4>Links</h4>
                    <a href="https://github.com/your-username/emergence" target="_blank" rel="noopener noreferrer">
                        <Github size={14} /> GitHub
                    </a>
                    <a href="https://twitter.com/your-handle" target="_blank" rel="noopener noreferrer">
                        <Twitter size={14} /> Twitter
                    </a>
                </div>

                <div className="footer-section">
                    <h4>Support</h4>
                    <p className="footer-support-text">
                        This experiment costs ~$30/month to run.
                    </p>
                    <a
                        href="https://github.com/sponsors/your-username"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="sponsor-link"
                    >
                        <Heart size={14} /> Sponsor on GitHub
                    </a>
                    <a
                        href="https://opencollective.com/emergence"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="sponsor-link"
                    >
                        <ExternalLink size={14} /> Open Collective
                    </a>
                </div>
            </div>

            <div className="footer-bottom">
                <span>© 2025 Emergence Project</span>
                <span className="footer-separator">•</span>
                <span>MIT License</span>
                <span className="footer-separator">•</span>
                <span>Made with curiosity</span>
            </div>

            <style>{`
        .site-footer {
          margin-top: auto;
          padding: var(--spacing-xl) var(--spacing-lg);
          border-top: 1px solid var(--border-color);
          background: var(--bg-secondary);
        }
        
        .footer-content {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: var(--spacing-xl);
          margin-bottom: var(--spacing-lg);
        }
        
        .footer-section h4 {
          font-size: 0.75rem;
          text-transform: uppercase;
          color: var(--text-muted);
          margin-bottom: var(--spacing-md);
          letter-spacing: 0.05em;
        }
        
        .footer-logo {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          margin-bottom: var(--spacing-sm);
        }
        
        .logo-icon-small {
          width: 24px;
          height: 24px;
          background: var(--gradient-primary);
          border-radius: var(--radius-sm);
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 0.75rem;
        }
        
        .footer-tagline {
          font-size: 0.8125rem;
          color: var(--text-muted);
        }
        
        .footer-section a {
          display: flex;
          align-items: center;
          gap: var(--spacing-sm);
          color: var(--text-secondary);
          font-size: 0.875rem;
          padding: var(--spacing-xs) 0;
        }
        
        .footer-section a:hover {
          color: var(--text-primary);
        }
        
        .footer-support-text {
          font-size: 0.8125rem;
          color: var(--text-muted);
          margin-bottom: var(--spacing-sm);
        }
        
        .sponsor-link {
          color: var(--accent-purple) !important;
        }
        
        .sponsor-link:hover {
          color: var(--accent-pink) !important;
        }
        
        .footer-bottom {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: var(--spacing-sm);
          font-size: 0.75rem;
          color: var(--text-muted);
          padding-top: var(--spacing-lg);
          border-top: 1px solid var(--border-color);
        }
        
        .footer-separator {
          opacity: 0.5;
        }
        
        @media (max-width: 768px) {
          .footer-content {
            grid-template-columns: 1fr;
            text-align: center;
          }
          
          .footer-logo {
            justify-content: center;
          }
          
          .footer-section a {
            justify-content: center;
          }
        }
      `}</style>
        </footer>
    )
}
