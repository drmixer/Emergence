import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Activity, BookOpen, ChevronRight, FileSearch, Sparkles, Star, X } from 'lucide-react'
import './FirstTimeOnboarding.css'

const ONBOARDING_STORAGE_KEY = 'emergence-first-time-onboarding-v1'

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
    const open = !dismissed && !path.startsWith('/ops')

    const close = (reason) => {
        writeOnboardingState(reason || 'dismissed')
        setDismissed(true)
    }

    const handleStart = () => {
        close('completed')
        navigate('/dashboard')
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
                    Runs are live simulations. Use these surfaces first so the story and evidence are immediately clear.
                </p>

                <ul className="onboarding-steps">
                    <li>
                        <Activity size={14} />
                        <span><strong>Dashboard:</strong> live state, crises, and momentum.</span>
                    </li>
                    <li>
                        <Star size={14} />
                        <span><strong>Highlights:</strong> replay major moments in sequence.</span>
                    </li>
                    <li>
                        <FileSearch size={14} />
                        <span><strong>Reports:</strong> technical and story outputs with evidence links.</span>
                    </li>
                    <li>
                        <BookOpen size={14} />
                        <span><strong>Glossary:</strong> quick definitions for run/season/epoch terms.</span>
                    </li>
                </ul>

                <div className="onboarding-actions">
                    <button type="button" className="btn btn-secondary" onClick={() => close('dismissed')}>
                        Skip
                    </button>
                    <button type="button" className="btn btn-primary" onClick={handleStart}>
                        Open Dashboard
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
