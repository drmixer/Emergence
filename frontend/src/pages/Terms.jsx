export default function Terms() {
  return (
    <div className="about-page">
      <div className="page-header">
        <h1>Terms of Use</h1>
        <p className="page-description">Conditions for using the Emergence site and materials</p>
      </div>

      <div className="about-content">
        <div className="card">
          <div className="card-body">
            <h2>Acceptance</h2>
            <p>
              By using Emergence, you agree to these terms. If you do not agree, do not use the site.
            </p>

            <h3>Research Context</h3>
            <ul>
              <li>Emergence is an observational AI simulation project, not legal, financial, or safety advice.</li>
              <li>Published outputs are context-dependent and may change with new runs or parameter updates.</li>
            </ul>

            <h3>Permitted Use</h3>
            <ul>
              <li>You may browse and reference public pages and dashboards for non-abusive purposes.</li>
              <li>You may not attempt to disrupt service availability or interfere with infrastructure.</li>
            </ul>

            <h3>Intellectual Property</h3>
            <p>
              Code and assets are governed by their repository licenses. Third-party service names and trademarks
              remain the property of their owners.
            </p>

            <h3>No Warranty</h3>
            <p>
              The service is provided on an “as is” basis without warranties of availability, fitness, or error-free operation.
            </p>

            <h3>Limitation of Liability</h3>
            <p>
              To the maximum extent permitted by law, project maintainers are not liable for indirect, incidental, or consequential damages
              arising from use of the service.
            </p>

            <h3>Updates</h3>
            <p>
              Terms may be updated over time. Continued use after updates constitutes acceptance of the revised terms.
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
