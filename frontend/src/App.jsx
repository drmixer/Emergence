import { Suspense, createElement, lazy, useEffect, useState } from 'react'
import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import {
  Activity,
  Users,
  MessageSquare,
  FileText,
  Scale,
  Package,
  ExternalLink,
  Github,
  FileSearch,
  Info,
  Menu,
  X,
  Share2,
  TrendingUp,
  BookOpen,
} from 'lucide-react'

// Pages (route-level code splitting)
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Agents = lazy(() => import('./pages/Agents'))
const Agent = lazy(() => import('./pages/Agent'))
const Messages = lazy(() => import('./pages/Messages'))
const Governance = lazy(() => import('./pages/Governance'))
const Proposals = lazy(() => import('./pages/Proposals'))
const Laws = lazy(() => import('./pages/Laws'))
const Resources = lazy(() => import('./pages/Resources'))
const About = lazy(() => import('./pages/About'))
const HighlightsCompatibility = lazy(() => import('./pages/HighlightsCompatibility'))
const Leaderboards = lazy(() => import('./pages/Leaderboards'))
const Network = lazy(() => import('./pages/Network'))
const Timeline = lazy(() => import('./pages/Timeline'))
const Predictions = lazy(() => import('./pages/Predictions'))
const Ops = lazy(() => import('./pages/Ops'))
const Method = lazy(() => import('./pages/Method'))
const Glossary = lazy(() => import('./pages/Glossary'))
const RunDetail = lazy(() => import('./pages/RunDetail'))
const RunReplay = lazy(() => import('./pages/RunReplay'))
const ReportViewer = lazy(() => import('./pages/ReportViewer'))
const Reports = lazy(() => import('./pages/Reports'))
const Privacy = lazy(() => import('./pages/Privacy'))
const Terms = lazy(() => import('./pages/Terms'))

// Components
const LiveFeed = lazy(() => import('./components/LiveFeed'))
const FirstTimeOnboarding = lazy(() => import('./components/FirstTimeOnboarding'))
const ToastProvider = lazy(() => import('./components/ToastNotifications'))
const KeyboardNavigationListener = lazy(() => import('./components/KeyboardNavigationListener'))
import SupportBanner from './components/SupportBanner'
import { SubscriptionProvider, NotificationBell } from './components/Subscriptions'

const APP_ICON_LINKS = [
  { rel: 'icon', href: '/logo.png', type: 'image/png' },
  { rel: 'shortcut icon', href: '/logo.png', type: 'image/png' },
  { rel: 'apple-touch-icon', href: '/logo.png' },
]

function opsUiEnabled() {
  const envValue = String(
    import.meta.env?.VITE_ENABLE_OPS_UI || import.meta.env?.NEXT_PUBLIC_ENABLE_OPS_UI || ''
  ).toLowerCase()
  if (envValue === 'true') return true
  if (envValue === 'false') return false
  if (typeof window === 'undefined') return false
  return ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname)
}

function NotFound() {
  return (
    <div className="page-container">
      <div className="error-state">
        <h1>Not found</h1>
        <p>This page is not available.</p>
      </div>
    </div>
  )
}

function syncAppIcons() {
  if (typeof document === 'undefined') return

  APP_ICON_LINKS.forEach(({ rel, href, type }) => {
    let link = document.head.querySelector(`link[rel="${rel}"]`)
    if (!link) {
      link = document.createElement('link')
      link.rel = rel
      document.head.appendChild(link)
    }
    if (type) {
      link.type = type
    } else {
      link.removeAttribute('type')
    }
    link.href = href
  })
}

function App() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const location = useLocation()
  const showLiveFeedSidebar = location.pathname === '/dashboard'

  useEffect(() => {
    syncAppIcons()
  }, [])

  const navItems = [
    { path: '/dashboard', icon: Activity, label: 'Current Run' },
    { path: '/agents', icon: Users, label: 'Agents' },
    { path: '/messages', icon: MessageSquare, label: 'Messages' },
    { path: '/network', icon: Share2, label: 'Network' },
    { path: '/governance', icon: Scale, label: 'Governance' },
    { path: '/resources', icon: Package, label: 'Resources' },
    { path: '/archive', icon: FileSearch, label: 'Archive' },
    { path: '/predictions', icon: TrendingUp, label: 'Predictions' },
    { path: '/glossary', icon: BookOpen, label: 'Glossary' },
  ]

  const handleNavClick = () => {
    setMobileMenuOpen(false)
  }

  const routeLoadingFallback = <div className="page-loading">Loading page...</div>

  return (
    <SubscriptionProvider>
      <div className="app-wrapper">
        <SupportBanner />
        <Suspense fallback={null}>
          <KeyboardNavigationListener />
        </Suspense>
        <Suspense fallback={null}>
          <FirstTimeOnboarding />
        </Suspense>

        {/* Mobile Header */}
        <header className="mobile-header">
          <a href="/" className="mobile-logo">
            <img src="/logo.png" alt="Emergence" className="mobile-logo-img" />
            <span>Emergence</span>
          </a>
          <div className="mobile-header-actions">
            <NotificationBell />
            <button
              className="mobile-menu-toggle"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label="Toggle menu"
            >
              {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </header>

        {/* Mobile Navigation Overlay */}
        {mobileMenuOpen && (
          <div className="mobile-nav-overlay" onClick={() => setMobileMenuOpen(false)} />
        )}

        {/* Mobile Navigation Drawer */}
        <nav className={`mobile-nav ${mobileMenuOpen ? 'open' : ''}`}>
          <div className="mobile-nav-header">
            <a href="/" className="logo" onClick={handleNavClick}>
              <img src="/logo.png" alt="Emergence" className="logo-icon-img" />
              <div className="logo-text">
                <span className="logo-title">Emergence</span>
                <span className="logo-subtitle">AI Civilization</span>
              </div>
            </a>
          </div>
          <div className="mobile-nav-items">
            {navItems.map(({ path, icon, label }) => (
              <NavLink
                key={path}
                to={path}
                className={({ isActive }) =>
                  `nav-item ${isActive ? 'active' : ''}`
                }
                end={path === '/dashboard'}
                onClick={handleNavClick}
              >
                {createElement(icon, { size: 20 })}
                <span>{label}</span>
              </NavLink>
            ))}
            <div className="mobile-nav-divider" />
            <a href="https://github.com/drmixer/Emergence" target="_blank" rel="noopener noreferrer" className="nav-item" onClick={handleNavClick}>
              <Github size={20} />
              <span>GitHub</span>
              <ExternalLink size={14} className="external-icon" />
            </a>
            <NavLink to="/about" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} onClick={handleNavClick}>
              <Info size={20} />
              <span>About</span>
            </NavLink>
            <NavLink to="/privacy" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} onClick={handleNavClick}>
              <BookOpen size={20} />
              <span>Privacy</span>
            </NavLink>
            <NavLink to="/terms" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} onClick={handleNavClick}>
              <FileText size={20} />
              <span>Terms</span>
            </NavLink>
          </div>
        </nav>

        <div className={`app ${showLiveFeedSidebar ? '' : 'no-feed-sidebar'}`}>
          {/* Sidebar Navigation */}
          <aside className="sidebar">
            <div className="sidebar-header">
              <a href="/" className="logo">
                <img src="/logo.png" alt="Emergence" className="logo-icon-img" />
                <div className="logo-text">
                  <span className="logo-title">Emergence</span>
                  <span className="logo-subtitle">AI Civilization</span>
                </div>
              </a>
              <NotificationBell />
            </div>

            <nav className="sidebar-nav">
              {navItems.map(({ path, icon, label }) => (
                <NavLink
                  key={path}
                  to={path}
                  className={({ isActive }) =>
                    `nav-item ${isActive ? 'active' : ''}`
                  }
                  end={path === '/dashboard'}
                >
                  {createElement(icon, { size: 20 })}
                  <span>{label}</span>
                </NavLink>
              ))}
            </nav>

            <div className="sidebar-footer">
              <a href="https://github.com/drmixer/Emergence" target="_blank" rel="noopener noreferrer" className="nav-item">
                <Github size={20} />
                <span>GitHub</span>
                <ExternalLink size={14} className="external-icon" />
              </a>
              <NavLink to="/about" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                <Info size={20} />
                <span>About</span>
              </NavLink>
              <NavLink to="/privacy" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                <BookOpen size={20} />
                <span>Privacy</span>
              </NavLink>
              <NavLink to="/terms" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
                <FileText size={20} />
                <span>Terms</span>
              </NavLink>
            </div>
          </aside>

          {/* Main Content */}
          <main className="main-content">
            <Suspense fallback={routeLoadingFallback}>
              <Routes>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/agents" element={<Agents />} />
                <Route path="/agents/:id" element={<Agent />} />
                <Route path="/messages" element={<Messages />} />
                <Route path="/governance" element={<Governance />} />
                <Route path="/proposals" element={<Proposals />} />
                <Route path="/laws" element={<Laws />} />
                <Route path="/resources" element={<Resources />} />
                <Route path="/network" element={<Network />} />
                <Route path="/timeline" element={<Timeline />} />
                <Route path="/highlights" element={<HighlightsCompatibility />} />
                <Route path="/archive" element={<Reports />} />
                <Route path="/reports" element={<Reports />} />
                <Route path="/leaderboards" element={<Leaderboards />} />
                <Route path="/predictions" element={<Predictions />} />
                <Route path="/about" element={<About />} />
                <Route path="/method" element={<Method />} />
                <Route path="/glossary" element={<Glossary />} />
                <Route path="/privacy" element={<Privacy />} />
                <Route path="/terms" element={<Terms />} />
                <Route path="/ops" element={opsUiEnabled() ? <Ops /> : <NotFound />} />
                <Route path="/runs/:runId/replay" element={<RunReplay />} />
                <Route path="/runs/:runId/reports/:artifactType" element={<ReportViewer />} />
                <Route path="/runs/:runId" element={<RunDetail />} />
              </Routes>
            </Suspense>
          </main>

          {showLiveFeedSidebar && (
            <aside className="feed-sidebar">
              <Suspense fallback={<div className="feed-loading">Loading feed...</div>}>
                <LiveFeed />
              </Suspense>
            </aside>
          )}
        </div>
        <Suspense fallback={null}>
          <ToastProvider />
        </Suspense>
      </div>
    </SubscriptionProvider>
  )
}

export default App
