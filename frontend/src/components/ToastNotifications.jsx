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

const maxVisibleEventToasts = 3
const activeEventToastIds = []

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

function isProposalToast(event) {
    const eventType = event?.event_type || event?.type
    return eventType === 'proposal_created' || eventType === 'create_proposal'
}

// Custom toast component for events
function EventToast({ event, config }) {
    const Icon = config?.icon || MessageSquare
    const color = config?.color || '#6B7280'
    const bgColor = config?.bgColor || 'rgba(107, 114, 128, 0.15)'
    const prefix = config?.prefix || ''
    const proposalToast = isProposalToast(event)

    return (
        <div
            className={`event-toast ${proposalToast ? 'proposal-toast' : ''}`}
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
    const proposalToast = isProposalToast(event)

    // Only show toasts for notable events
    const notableTypes = [
        'law_passed',
        'proposal_created',
        'create_proposal',
        'enforcement_initiated',
        'vote_enforcement',
        'resources_seized',
        'agent_sanctioned',
        'agent_exiled',
        'agent_dormant',
        'became_dormant',
        'crisis',
        'world_event',
        'resource_critical',
        'trade',
        'milestone',
        'awakened'
    ]

    if (!notableTypes.includes(event.event_type) && !notableTypes.includes(event.type)) {
        return
    }

    while (activeEventToastIds.length >= maxVisibleEventToasts) {
        const oldestToastId = activeEventToastIds.shift()
        if (oldestToastId) {
            toast.dismiss(oldestToastId)
        }
    }

    const toastId = toast.custom(
        (t) => (
            <div
                className={`toast-wrapper ${t.visible ? 'toast-enter' : 'toast-exit'}`}
                onClick={() => toast.dismiss(t.id)}
            >
                <EventToast event={event} config={config} />
            </div>
        ),
        {
            id: proposalToast ? 'proposal-feed-toast' : undefined,
            duration: proposalToast ? 3500 : 5000,
            position: 'bottom-right',
        }
    )
    activeEventToastIds.push(toastId)
    window.setTimeout(() => {
        const index = activeEventToastIds.indexOf(toastId)
        if (index >= 0) {
            activeEventToastIds.splice(index, 1)
        }
    }, proposalToast ? 3800 : 5300)
}

// Hook to subscribe to SSE events and show toasts
export function useEventToasts(enabled = true) {
    const [lastEventId, setLastEventId] = useState(null)

    const handleEvent = useCallback((event) => {
        if (event.type === 'event' && !event.snapshot_replay && event.id !== lastEventId) {
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
                gutter={10}
                containerStyle={{
                    right: 24,
                    bottom: 24,
                }}
                toastOptions={{
                    duration: 5000,
                }}
            />
            <style>{`
                .event-toast {
                    display: flex;
                    align-items: flex-start;
                    gap: 12px;
                    padding: 12px 14px;
                    background: rgba(10, 10, 10, 0.92);
                    border: 1px solid color-mix(in srgb, var(--toast-color) 55%, transparent);
                    border-radius: 12px;
                    box-shadow: 0 10px 32px rgba(0, 0, 0, 0.34);
                    backdrop-filter: blur(12px);
                    max-width: 320px;
                    cursor: pointer;
                    transition: all 0.2s ease;
                }

                .proposal-toast {
                    gap: 10px;
                    max-width: 280px;
                    padding: 10px 12px;
                }

                .event-toast:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.42);
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

                .proposal-toast .toast-icon {
                    width: 28px;
                    height: 28px;
                    border-radius: 7px;
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
                    overflow: hidden;
                    display: -webkit-box;
                    -webkit-box-orient: vertical;
                    -webkit-line-clamp: 3;
                }

                .proposal-toast .toast-message {
                    font-size: 0.8125rem;
                    line-height: 1.35;
                    -webkit-line-clamp: 2;
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

                @media (max-width: 900px) {
                    .event-toast,
                    .proposal-toast {
                        max-width: min(300px, calc(100vw - 32px));
                    }
                }
            `}</style>
        </>
    )
}

export default ToastProvider
