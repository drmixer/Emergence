import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { CalendarDays, ChevronRight, Eye, FileSearch, Sparkles, X } from 'lucide-react'
import { trackKpiEvent, trackKpiEventOnce } from '../services/kpiAnalytics'
import './FirstTimeOnboarding.css'

const ONBOARDING_STORAGE_KEY = 'emergence-first-time-onboarding-v1'
const ONBOARDING_AUTO_OPEN_PATHS = new Set(['/', '/dashboard'])

export function shouldAutoOpenOnboarding(pathname) {
    const path = String(pathname || '').trim().toLowerCase() || '/'
    return ONBOARDING_AUTO_OPEN_PATHS.has(path)
}

function readOnboardingState() {
    try {
        return Boolean(localStorage.getItem(ONBOARDING_STORAGE_KEY))
    } catch {
        return true
    }
}

function writeOnboardingState(value) {
    try {
        localStorage.setItem(ONBOARDING_STORAGE_KEY, String(value))
    } catch {
        // Ignore storage failures for privacy modes.
    }
}

export default function FirstTimeOnboarding() {
    const location = useLocation()
    const navigate = useNavigate()
    const [dismissed, setDismissed] = useState(readOnboardingState)
    const path = String(location.pathname || '').trim().toLowerCase()
    const open = !dismissed && shouldAutoOpenOnboarding(path)

    useEffect(() => {
        if (!open) return
        trackKpiEventOnce('onboarding_shown', 'first_time_onboarding_v1', {
            surface: 'onboarding_modal',
            target: 'modal_impression',
            metadata: { version: 'v1' },
        })
    }, [open])

    const close = (reason) => {
        if (reason === 'completed') {
            trackKpiEvent('onboarding_completed', {
                surface: 'onboarding_modal',
                target: 'open_archive',
                metadata: { version: 'v1' },
            })
        } else if (reason === 'glossary') {
            trackKpiEvent('onboarding_glossary_opened', {
                surface: 'onboarding_modal',
                target: 'open_glossary',
                metadata: { version: 'v1' },
            })
        } else {
            trackKpiEvent('onboarding_skipped', {
                surface: 'onboarding_modal',
                target: 'dismiss',
                metadata: { version: 'v1', reason: String(reason || 'dismissed') },
            })
        }
        writeOnboardingState(reason || 'dismissed')
        setDismissed(true)
    }

    const handleStart = () => {
        close('completed')
        navigate('/archive')
    }

    if (!open) return null

    return (
        <div className="onboarding-overlay" onClick={() => close('dismissed')}>
            <section
                className="onboarding-card"
                role="dialog"
                aria-modal="true"
                aria-labelledby="onboarding-title"
                onClick={(event) => event.stopPropagation()}
            >
                <button className="onboarding-close" aria-label="Close onboarding" onClick={() => close('dismissed')}>
                    <X size={16} />
                </button>

                <div className="onboarding-header">
                    <Sparkles size={16} />
                    <span>Quick Viewer Guide</span>
                </div>

                <h3 id="onboarding-title">How to read Emergence in under a minute</h3>
                <p className="onboarding-copy">
                    Runs are live simulations. Start with the latest brief, then use the map, replay, and source evidence.
                </p>

                <ul className="onboarding-steps">
                    <li>
                        <FileSearch size={14} />
                        <span><strong>Archive:</strong> choose a completed run and read the brief first.</span>
                    </li>
                    <li>
                        <Eye size={14} />
                        <span><strong>Watch Map and Replay:</strong> timeline map first, then selected moment walkthroughs.</span>
                    </li>
                    <li>
                        <FileSearch size={14} />
                        <span><strong>Evidence:</strong> source audit trail for claims, not the normal first stop.</span>
                    </li>
                    <li>
                        <CalendarDays size={14} />
                        <span><strong>Calendar and Field Notes:</strong> run context, schedule, and post-run writing.</span>
                    </li>
                </ul>

                <div className="onboarding-actions">
                    <button type="button" className="btn btn-secondary" onClick={() => close('dismissed')}>
                        Skip
                    </button>
                    <button type="button" className="btn btn-primary" onClick={handleStart}>
                        Start with Archive
                        <ChevronRight size={14} />
                    </button>
                </div>

                <p className="onboarding-footnote">
                    Need definitions first?{' '}
                    <Link to="/glossary" onClick={() => close('glossary')}>
                        Open the glossary
                    </Link>
                    .
                </p>
            </section>
        </div>
    )
}
