import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { CircleHelp } from 'lucide-react'
import { GLOSSARY_TERMS_BY_KEY } from '../data/glossaryTerms'
import './GlossaryTooltip.css'

export default function GlossaryTooltip({
    termKey,
    children,
    className = '',
}) {
    const entry = GLOSSARY_TERMS_BY_KEY[termKey]
    const [open, setOpen] = useState(false)
    const wrapperRef = useRef(null)
    const closeTimerRef = useRef(null)
    const tooltipId = useId()

    const cancelClose = () => {
        if (closeTimerRef.current) {
            clearTimeout(closeTimerRef.current)
            closeTimerRef.current = null
        }
    }

    const scheduleClose = () => {
        cancelClose()
        closeTimerRef.current = setTimeout(() => {
            setOpen(false)
            closeTimerRef.current = null
        }, 140)
    }

    useEffect(() => {
        if (!open) return undefined
        const handlePointerDown = (event) => {
            if (!wrapperRef.current?.contains(event.target)) {
                setOpen(false)
            }
        }
        const handleEscape = (event) => {
            if (event.key === 'Escape') setOpen(false)
        }
        document.addEventListener('pointerdown', handlePointerDown)
        document.addEventListener('keydown', handleEscape)
        return () => {
            document.removeEventListener('pointerdown', handlePointerDown)
            document.removeEventListener('keydown', handleEscape)
        }
    }, [open])

    useEffect(() => () => cancelClose(), [])

    if (!entry) {
        return <span className={className}>{children || termKey}</span>
    }

    return (
        <span
            className={`glossary-inline ${open ? 'open' : ''} ${className}`}
            ref={wrapperRef}
            onMouseEnter={() => {
                cancelClose()
                setOpen(true)
            }}
            onMouseLeave={scheduleClose}
        >
            <button
                type="button"
                className="glossary-trigger"
                aria-haspopup="dialog"
                aria-expanded={open}
                aria-controls={tooltipId}
                onClick={() => {
                    cancelClose()
                    setOpen((prev) => !prev)
                }}
                onFocus={() => {
                    cancelClose()
                    setOpen(true)
                }}
                onBlur={scheduleClose}
            >
                <span className="glossary-trigger-label">{children || entry.shortLabel}</span>
                <CircleHelp size={12} />
            </button>

            <span
                id={tooltipId}
                role="dialog"
                className={`glossary-popover ${open ? 'visible' : ''}`}
                onMouseEnter={cancelClose}
                onMouseLeave={scheduleClose}
            >
                <span className="glossary-popover-title">{entry.label}</span>
                <span className="glossary-popover-body">{entry.definition}</span>
                <Link
                    className="glossary-popover-link"
                    to={`/glossary#${entry.key}`}
                    onClick={() => setOpen(false)}
                >
                    Learn more
                </Link>
            </span>
        </span>
    )
}
