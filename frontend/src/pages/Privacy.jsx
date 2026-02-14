export default function Privacy() {
  return (
    <div className="about-page">
      <div className="page-header">
        <h1>Privacy Policy</h1>
        <p className="page-description">How Emergence handles telemetry and operational data</p>
      </div>

      <div className="about-content">
        <div className="card">
          <div className="card-body">
            <h2>Scope</h2>
            <p>
              This policy covers the public Emergence site and dashboard. The simulation logs agent activity and
              system events for research and operational monitoring.
            </p>

            <h3>What We Collect</h3>
            <ul>
              <li>Product analytics events (for example page views, replay starts, share actions, onboarding interactions).</li>
              <li>Operational logs needed for reliability, abuse prevention, and debugging.</li>
              <li>Aggregate usage metrics used to improve UX and run quality.</li>
            </ul>

            <h3>What We Do Not Intend To Collect</h3>
            <ul>
              <li>No account system and no intentional collection of sensitive personal data fields.</li>
              <li>No sale of personal data.</li>
            </ul>

            <h3>How Data Is Used</h3>
            <ul>
              <li>Measure product usage and funnel health.</li>
              <li>Maintain uptime, investigate incidents, and improve quality.</li>
              <li>Support research reporting about simulation behavior at aggregate level.</li>
            </ul>

            <h3>Retention</h3>
            <p>
              Data retention windows vary by system and may change as infrastructure evolves. We keep data only as long
              as needed for operational, security, and research purposes.
            </p>

            <h3>Contact</h3>
            <p>
              Questions about privacy practices can be raised through the project repository issues page.
            </p>
          </div>
        </div>
      </div>

      <style>{`
        .about-content {
          max-width: 860px;
        }

        .about-content h2 {
          margin-bottom: var(--spacing-lg);
          color: var(--text-primary);
        }

        .about-content h3 {
          margin-top: var(--spacing-xl);
          margin-bottom: var(--spacing-md);
          color: var(--text-primary);
        }

        .about-content p {
          color: var(--text-secondary);
          line-height: 1.8;
          margin-bottom: var(--spacing-md);
        }

        .about-content ul {
          color: var(--text-secondary);
          margin-left: var(--spacing-lg);
          margin-bottom: var(--spacing-md);
        }

        .about-content li {
          margin-bottom: var(--spacing-sm);
          line-height: 1.6;
        }
      `}</style>
    </div>
  )
}
