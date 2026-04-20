import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { createPortal } from 'react-dom'
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
    const [placement, setPlacement] = useState('center')
    const [verticalPlacement, setVerticalPlacement] = useState('bottom')
    const [popoverStyle, setPopoverStyle] = useState(null)
    const wrapperRef = useRef(null)
    const tooltipRef = useRef(null)
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

        const updatePlacement = () => {
            const wrapper = wrapperRef.current
            if (!wrapper) return
            const rect = wrapper.getBoundingClientRect()
            const margin = 12
            const viewportWidth = window.innerWidth
            const viewportHeight = window.innerHeight
            const estimatedWidth = Math.min(320, Math.max(160, viewportWidth - margin * 2))
            const estimatedHeight = tooltipRef.current?.offsetHeight || 156
            const centeredLeft = rect.left + rect.width / 2 - estimatedWidth / 2
            const preferredLeft = Math.min(
                Math.max(centeredLeft, margin),
                viewportWidth - estimatedWidth - margin
            )
            const preferredTop = rect.bottom + 8
            const aboveTop = rect.top - estimatedHeight - 8
            const shouldPlaceAbove =
                preferredTop + estimatedHeight > viewportHeight - margin &&
                aboveTop >= margin

            if (centeredLeft < margin) {
                setPlacement('left')
            } else if (centeredLeft + estimatedWidth > viewportWidth - margin) {
                setPlacement('right')
            } else {
                setPlacement('center')
            }

            setVerticalPlacement(shouldPlaceAbove ? 'top' : 'bottom')
            setPopoverStyle({
                left: `${preferredLeft}px`,
                top: `${Math.max(
                    margin,
                    shouldPlaceAbove
                        ? aboveTop
                        : Math.min(preferredTop, viewportHeight - estimatedHeight - margin)
                )}px`,
                width: `${estimatedWidth}px`,
            })
        }

        updatePlacement()
        const frame = window.requestAnimationFrame(updatePlacement)

        const handlePointerDown = (event) => {
            const clickedTrigger = wrapperRef.current?.contains(event.target)
            const clickedTooltip = tooltipRef.current?.contains(event.target)
            if (!clickedTrigger && !clickedTooltip) {
                setOpen(false)
            }
        }
        const handleEscape = (event) => {
            if (event.key === 'Escape') setOpen(false)
        }
        window.addEventListener('resize', updatePlacement)
        window.addEventListener('scroll', updatePlacement, true)
        document.addEventListener('pointerdown', handlePointerDown)
        document.addEventListener('keydown', handleEscape)
        return () => {
            window.cancelAnimationFrame(frame)
            window.removeEventListener('resize', updatePlacement)
            window.removeEventListener('scroll', updatePlacement, true)
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

            {open && typeof document !== 'undefined' && createPortal(
                <span
                    id={tooltipId}
                    ref={tooltipRef}
                    role="dialog"
                    className={`glossary-popover glossary-popover-${placement} glossary-popover-${verticalPlacement} visible`}
                    style={popoverStyle || undefined}
                    onMouseEnter={cancelClose}
                    onMouseLeave={scheduleClose}
                    onFocus={cancelClose}
                    onBlur={scheduleClose}
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
                </span>,
                document.body
            )}
        </span>
    )
}
