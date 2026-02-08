import { createElement, useState } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import {
  Activity,
  Users,
  FileText,
  Scale,
  Package,
  ExternalLink,
  Github,
  Star,
  Trophy,
  Info,
  Menu,
  X,
  Share2,
  Calendar,
  TrendingUp,
  Shield,
} from 'lucide-react'

// Pages
import Dashboard from './pages/Dashboard'
import Agents from './pages/Agents'
import Agent from './pages/Agent'
import Proposals from './pages/Proposals'
import Laws from './pages/Laws'
import Resources from './pages/Resources'
import About from './pages/About'
import Highlights from './pages/Highlights'
import Leaderboards from './pages/Leaderboards'
import Network from './pages/Network'
import Timeline from './pages/Timeline'
import Predictions from './pages/Predictions'
import Ops from './pages/Ops'
import Method from './pages/Method'

// Components
import LiveFeed from './components/LiveFeed'
import SupportBanner from './components/SupportBanner'
import ToastProvider from './components/ToastNotifications'
import { useKeyboardNavigation } from './components/KeyboardNavigation'
import { SubscriptionProvider, NotificationBell } from './components/Subscriptions'


function App() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  // Enable keyboard navigation
  useKeyboardNavigation()

  const navItems = [
    { path: '/dashboard', icon: Activity, label: 'Dashboard' },
    { path: '/agents', icon: Users, label: 'Agents' },
    { path: '/network', icon: Share2, label: 'Network' },
    { path: '/proposals', icon: FileText, label: 'Proposals' },
    { path: '/laws', icon: Scale, label: 'Laws' },
    { path: '/resources', icon: Package, label: 'Resources' },
    { path: '/timeline', icon: Calendar, label: 'Timeline' },
    { path: '/highlights', icon: Star, label: 'Highlights' },
    { path: '/predictions', icon: TrendingUp, label: 'Predictions' },
    { path: '/leaderboards', icon: Trophy, label: 'Leaderboards' },
    { path: '/ops', icon: Shield, label: 'Ops' },
  ]

  const handleNavClick = () => {
    setMobileMenuOpen(false)
  }

  return (
    <SubscriptionProvider>
      <div className="app-wrapper">
        <SupportBanner />

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
          </div>
        </nav>

        <div className="app">
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
            </div>
          </aside>

          {/* Main Content */}
          <main className="main-content">
            <Routes>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/agents" element={<Agents />} />
              <Route path="/agents/:id" element={<Agent />} />
              <Route path="/proposals" element={<Proposals />} />
              <Route path="/laws" element={<Laws />} />
              <Route path="/resources" element={<Resources />} />
              <Route path="/network" element={<Network />} />
              <Route path="/timeline" element={<Timeline />} />
              <Route path="/highlights" element={<Highlights />} />
              <Route path="/leaderboards" element={<Leaderboards />} />
              <Route path="/predictions" element={<Predictions />} />
              <Route path="/about" element={<About />} />
              <Route path="/method" element={<Method />} />
              <Route path="/ops" element={<Ops />} />
            </Routes>
          </main>

          {/* Live Feed Sidebar */}
          <aside className="feed-sidebar">
            <LiveFeed />
          </aside>
        </div>
        <ToastProvider />
      </div>
    </SubscriptionProvider>
  )
}

export default App
