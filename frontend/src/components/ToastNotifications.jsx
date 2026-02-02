// Toast Notifications for real-time alerts
import { useEffect, useCallback, useState } from 'react'
import toast, { Toaster } from 'react-hot-toast'
import {
    Scale,
    AlertTriangle,
    MessageSquare,
    Vote,
    Zap,
    Users,
    FileText,
    TrendingUp,
    Package
} from 'lucide-react'
import { subscribeToEvents } from '../services/api'

// Event type to icon/color mapping
const eventConfig = {
    law_passed: {
        icon: Scale,
        color: '#10B981',
        bgColor: 'rgba(16, 185, 129, 0.15)',
        prefix: '⚖️ New Law:'
    },
    proposal_created: {
        icon: FileText,
        color: '#3B82F6',
        bgColor: 'rgba(59, 130, 246, 0.15)',
        prefix: '📋 New Proposal:'
    },
    create_proposal: {
        icon: FileText,
        color: '#3B82F6',
        bgColor: 'rgba(59, 130, 246, 0.15)',
        prefix: '📋 New Proposal:'
    },
    agent_dormant: {
        icon: AlertTriangle,
        color: '#F59E0B',
        bgColor: 'rgba(245, 158, 11, 0.15)',
        prefix: '😴 Agent Dormant:'
    },
    became_dormant: {
        icon: AlertTriangle,
        color: '#F59E0B',
        bgColor: 'rgba(245, 158, 11, 0.15)',
        prefix: '😴 Agent Dormant:'
    },
    crisis: {
        icon: Zap,
        color: '#EF4444',
        bgColor: 'rgba(239, 68, 68, 0.15)',
        prefix: '🚨 Crisis:'
    },
    resource_critical: {
        icon: Package,
        color: '#EF4444',
        bgColor: 'rgba(239, 68, 68, 0.15)',
        prefix: '⚠️ Resource Critical:'
    },
    vote: {
        icon: Vote,
        color: '#8B5CF6',
        bgColor: 'rgba(139, 92, 246, 0.15)',
        prefix: '🗳️ Vote:'
    },
    milestone: {
        icon: TrendingUp,
        color: '#F59E0B',
        bgColor: 'rgba(245, 158, 11, 0.15)',
        prefix: '🎯 Milestone:'
    },
    awakened: {
        icon: Users,
        color: '#10B981',
        bgColor: 'rgba(16, 185, 129, 0.15)',
        prefix: '✨ Agent Awakened:'
    }
}

// Custom toast component for events
function EventToast({ event, config }) {
    const Icon = config?.icon || MessageSquare
    const color = config?.color || '#6B7280'
    const bgColor = config?.bgColor || 'rgba(107, 114, 128, 0.15)'
    const prefix = config?.prefix || ''

    return (
        <div
            className="event-toast"
            style={{
                '--toast-color': color,
                '--toast-bg': bgColor
            }}
        >
            <div className="toast-icon">
                <Icon size={18} />
            </div>
            <div className="toast-content">
                {prefix && <span className="toast-prefix">{prefix}</span>}
                <span className="toast-message">{event.description || event.message}</span>
            </div>
        </div>
    )
}

// Show a toast for an event
export function showEventToast(event) {
    const config = eventConfig[event.event_type] || eventConfig[event.type]

    // Only show toasts for notable events
    const notableTypes = [
        'law_passed',
        'proposal_created',
        'create_proposal',
        'agent_dormant',
        'became_dormant',
        'crisis',
        'resource_critical',
        'milestone',
        'awakened'
    ]

    if (!notableTypes.includes(event.event_type) && !notableTypes.includes(event.type)) {
        return
    }

    toast.custom(
        (t) => (
            <div
                className={`toast-wrapper ${t.visible ? 'toast-enter' : 'toast-exit'}`}
                onClick={() => toast.dismiss(t.id)}
            >
                <EventToast event={event} config={config} />
            </div>
        ),
        {
            duration: 5000,
            position: 'bottom-right',
        }
    )
}

// Hook to subscribe to SSE events and show toasts
export function useEventToasts(enabled = true) {
    const [lastEventId, setLastEventId] = useState(null)

    const handleEvent = useCallback((event) => {
        if (event.type === 'event' && event.id !== lastEventId) {
            setLastEventId(event.id)
            showEventToast(event)
        }
    }, [lastEventId])

    useEffect(() => {
        if (!enabled) return

        const unsubscribe = subscribeToEvents(
            handleEvent,
            (error) => {
                console.log('Toast subscription error:', error)
            }
        )

        return unsubscribe
    }, [enabled, handleEvent])
}

// Toast provider component with custom styling
export function ToastProvider() {
    return (
        <>
            <Toaster
                position="bottom-right"
                toastOptions={{
                    duration: 5000,
                }}
            />
            <style>{`
                .event-toast {
                    display: flex;
                    align-items: flex-start;
                    gap: 12px;
                    padding: 12px 16px;
                    background: var(--bg-card, #0a0a0a);
                    border: 1px solid var(--toast-color);
                    border-radius: 12px;
                    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
                    max-width: 360px;
                    cursor: pointer;
                    transition: all 0.2s ease;
                }

                .event-toast:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5);
                }

                .toast-icon {
                    width: 32px;
                    height: 32px;
                    border-radius: 8px;
                    background: var(--toast-bg);
                    color: var(--toast-color);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    flex-shrink: 0;
                }

                .toast-content {
                    flex: 1;
                    min-width: 0;
                }

                .toast-prefix {
                    display: block;
                    font-size: 0.75rem;
                    font-weight: 600;
                    color: var(--toast-color);
                    margin-bottom: 2px;
                    letter-spacing: 0.02em;
                }

                .toast-message {
                    font-size: 0.875rem;
                    color: rgba(255, 255, 255, 0.9);
                    line-height: 1.4;
                    display: block;
                }

                .toast-wrapper {
                    animation: toastEnter 0.3s ease;
                }

                .toast-wrapper.toast-exit {
                    animation: toastExit 0.3s ease forwards;
                }

                @keyframes toastEnter {
                    from {
                        opacity: 0;
                        transform: translateX(100px);
                    }
                    to {
                        opacity: 1;
                        transform: translateX(0);
                    }
                }

                @keyframes toastExit {
                    from {
                        opacity: 1;
                        transform: translateX(0);
                    }
                    to {
                        opacity: 0;
                        transform: translateX(100px);
                    }
                }
            `}</style>
        </>
    )
}

export default ToastProvider
