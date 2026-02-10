// Agent Subscriptions - Follow agents for updates
import { useState, useEffect, useCallback, createContext, useContext } from 'react'
import { Bell, BellOff, BellRing, Check, X, Star } from 'lucide-react'

// LocalStorage key for subscriptions
const STORAGE_KEY = 'emergence_subscriptions'

// Subscription Context for global state
const SubscriptionContext = createContext(null)

// Get subscriptions from localStorage
function getStoredSubscriptions() {
    try {
        const stored = localStorage.getItem(STORAGE_KEY)
        return stored ? JSON.parse(stored) : []
    } catch {
        return []
    }
}

// Save subscriptions to localStorage
function saveSubscriptions(subscriptions) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(subscriptions))
    } catch (e) {
        console.error('Failed to save subscriptions:', e)
    }
}

// Subscription Provider Component
export function SubscriptionProvider({ children }) {
    const [subscriptions, setSubscriptions] = useState(() => getStoredSubscriptions())
    const [notifications, setNotifications] = useState([])
    const [unreadCount, setUnreadCount] = useState(0)

    // Subscribe to an agent
    const subscribe = useCallback((agent) => {
        setSubscriptions(prev => {
            // Check if already subscribed
            if (prev.some(s => s.agent_number === agent.agent_number)) {
                return prev
            }

            const newSub = {
                agent_number: agent.agent_number,
                agent_id: agent.id,
                display_name: agent.display_name,
                personality: agent.personality,
                subscribed_at: new Date().toISOString()
            }

            const updated = [...prev, newSub]
            saveSubscriptions(updated)
            return updated
        })
    }, [])

    // Unsubscribe from an agent
    const unsubscribe = useCallback((agentNumber) => {
        setSubscriptions(prev => {
            const updated = prev.filter(s => s.agent_number !== agentNumber)
            saveSubscriptions(updated)
            return updated
        })
    }, [])

    // Check if subscribed to an agent
    const isSubscribed = useCallback((agentNumber) => {
        return subscriptions.some(s => s.agent_number === agentNumber)
    }, [subscriptions])

    // Add a notification
    const addNotification = useCallback((notification) => {
        // Only notify for subscribed agents
        if (!subscriptions.some(s => s.agent_number === notification.agent_number)) {
            return
        }

        setNotifications(prev => [{
            id: Date.now(),
            ...notification,
            read: false,
            created_at: new Date().toISOString()
        }, ...prev].slice(0, 50)) // Keep last 50

        setUnreadCount(prev => prev + 1)
    }, [subscriptions])

    // Mark notification as read
    const markAsRead = useCallback((notificationId) => {
        setNotifications(prev =>
            prev.map(n => n.id === notificationId ? { ...n, read: true } : n)
        )
        setUnreadCount(prev => Math.max(0, prev - 1))
    }, [])

    // Mark all as read
    const markAllAsRead = useCallback(() => {
        setNotifications(prev => prev.map(n => ({ ...n, read: true })))
        setUnreadCount(0)
    }, [])

    // Clear all notifications
    const clearNotifications = useCallback(() => {
        setNotifications([])
        setUnreadCount(0)
    }, [])

    const value = {
        subscriptions,
        notifications,
        unreadCount,
        subscribe,
        unsubscribe,
        isSubscribed,
        addNotification,
        markAsRead,
        markAllAsRead,
        clearNotifications
    }

    return (
        <SubscriptionContext.Provider value={value}>
            {children}
        </SubscriptionContext.Provider>
    )
}

// Hook to use subscriptions
export function useSubscriptions() {
    const context = useContext(SubscriptionContext)
    if (!context) {
        throw new Error('useSubscriptions must be used within a SubscriptionProvider')
    }
    return context
}

// Subscribe Button Component
export function SubscribeButton({ agent, size = 'medium', showLabel = true }) {
    const { subscribe, unsubscribe, isSubscribed } = useSubscriptions()
    const [animating, setAnimating] = useState(false)

    const subscribed = isSubscribed(agent.agent_number)

    const handleClick = (e) => {
        e.preventDefault()
        e.stopPropagation()

        setAnimating(true)

        if (subscribed) {
            unsubscribe(agent.agent_number)
        } else {
            subscribe(agent)
        }

        setTimeout(() => setAnimating(false), 300)
    }

    const sizeClasses = {
        small: 'subscribe-btn-sm',
        medium: 'subscribe-btn-md',
        large: 'subscribe-btn-lg'
    }

    return (
        <button
            className={`subscribe-btn ${sizeClasses[size]} ${subscribed ? 'subscribed' : ''} ${animating ? 'animating' : ''}`}
            onClick={handleClick}
            title={subscribed ? 'Unsubscribe' : 'Subscribe to updates'}
        >
            {subscribed ? (
                <>
                    <BellOff size={size === 'small' ? 14 : size === 'large' ? 20 : 16} />
                    {showLabel && <span>Following</span>}
                </>
            ) : (
                <>
                    <Bell size={size === 'small' ? 14 : size === 'large' ? 20 : 16} />
                    {showLabel && <span>Follow</span>}
                </>
            )}
        </button>
    )
}

// Notification Bell Component (for header)
export function NotificationBell() {
    const { notifications, unreadCount, markAsRead, markAllAsRead } = useSubscriptions()
    const [isOpen, setIsOpen] = useState(false)

    const toggleDropdown = () => setIsOpen(!isOpen)

    return (
        <div className="notification-bell-wrapper">
            <button
                className={`notification-bell ${unreadCount > 0 ? 'has-unread' : ''}`}
                onClick={toggleDropdown}
            >
                {unreadCount > 0 ? <BellRing size={20} /> : <Bell size={20} />}
                {unreadCount > 0 && (
                    <span className="notification-badge">{unreadCount > 9 ? '9+' : unreadCount}</span>
                )}
            </button>

            {isOpen && (
                <>
                    <div className="notification-overlay" onClick={() => setIsOpen(false)} />
                    <div className="notification-dropdown">
                        <div className="notification-header">
                            <h4>Notifications</h4>
                            {notifications.length > 0 && (
                                <button onClick={markAllAsRead} className="mark-all-read">
                                    Mark all read
                                </button>
                            )}
                        </div>

                        <div className="notification-list">
                            {notifications.length === 0 ? (
                                <div className="notification-empty">
                                    <Bell size={24} />
                                    <p>No notifications yet</p>
                                    <span>Follow agents to get updates</span>
                                </div>
                            ) : (
                                notifications.slice(0, 10).map(notification => (
                                    <div
                                        key={notification.id}
                                        className={`notification-item ${notification.read ? 'read' : 'unread'}`}
                                        onClick={() => markAsRead(notification.id)}
                                    >
                                        <div className="notification-icon">
                                            {notification.type === 'message' && <span>💬</span>}
                                            {notification.type === 'proposal' && <span>📋</span>}
                                            {notification.type === 'vote' && <span>🗳️</span>}
                                            {notification.type === 'dormant' && <span>💀</span>}
                                            {notification.type === 'awakened' && <span>✨</span>}
                                            {!notification.type && <span>📢</span>}
                                        </div>
                                        <div className="notification-content">
                                            <span className="notification-title">{notification.title}</span>
                                            <span className="notification-text">{notification.text}</span>
                                        </div>
                                        {!notification.read && <div className="unread-dot" />}
                                    </div>
                                ))
                            )}
                        </div>
                    </div>
                </>
            )}
        </div>
    )
}

// Watchlist Component - Shows all subscribed agents
export function Watchlist() {
    const { subscriptions, unsubscribe } = useSubscriptions()

    if (subscriptions.length === 0) {
        return (
            <div className="watchlist-empty">
                <Star size={32} />
                <h4>Your Watchlist</h4>
                <p>Follow agents to add them to your watchlist and receive updates when they take actions.</p>
            </div>
        )
    }

    return (
        <div className="watchlist">
            <div className="watchlist-header">
                <h4>Your Watchlist</h4>
                <span className="watchlist-count">{subscriptions.length} agent{subscriptions.length !== 1 ? 's' : ''}</span>
            </div>

            <div className="watchlist-items">
                {subscriptions.map(agent => (
                    <div key={agent.agent_number} className="watchlist-item">
                        <div className="watchlist-agent-info">
                            <span className="watchlist-agent-number">#{agent.agent_number}</span>
                            {agent.display_name && (
                                <span className="watchlist-agent-name">{agent.display_name}</span>
                            )}
                            {agent.personality && (
                                <span className={`watchlist-personality ${agent.personality}`}>
                                    {agent.personality}
                                </span>
                            )}
                        </div>
                        <button
                            className="watchlist-remove"
                            onClick={() => unsubscribe(agent.agent_number)}
                            title="Remove from watchlist"
                        >
                            <X size={14} />
                        </button>
                    </div>
                ))}
            </div>
        </div>
    )
}

// Hook to connect SSE events to subscriptions
export function useSubscriptionEvents(eventSource) {
    const { subscriptions, addNotification } = useSubscriptions()

    useEffect(() => {
        if (!eventSource) return

        const handleEvent = (event) => {
            try {
                const data = JSON.parse(event.data)

                // Check if this event involves a subscribed agent
                const agentNumber = data.agent_number || data.metadata?.agent_number

                if (!agentNumber) return

                const isSubscribed = subscriptions.some(s => s.agent_number === agentNumber)

                if (isSubscribed) {
                    // Create notification based on event type
                    let notification = null

                    switch (data.event_type || data.type) {
                        case 'forum_post':
                        case 'direct_message':
                            notification = {
                                agent_number: agentNumber,
                                type: 'message',
                                title: `Agent #${agentNumber} posted`,
                                text: data.content?.slice(0, 50) + '...' || 'New message'
                            }
                            break
                        case 'create_proposal':
                            notification = {
                                agent_number: agentNumber,
                                type: 'proposal',
                                title: `Agent #${agentNumber} created a proposal`,
                                text: data.title || 'New proposal'
                            }
                            break
                        case 'vote':
                            notification = {
                                agent_number: agentNumber,
                                type: 'vote',
                                title: `Agent #${agentNumber} voted`,
                                text: `Voted ${data.vote} on a proposal`
                            }
                            break
                        case 'became_dormant':
                            notification = {
                                agent_number: agentNumber,
                                type: 'dormant',
                                title: `Agent #${agentNumber} went dormant`,
                                text: 'They need help!'
                            }
                            break
                        case 'awakened':
                            notification = {
                                agent_number: agentNumber,
                                type: 'awakened',
                                title: `Agent #${agentNumber} awakened!`,
                                text: 'They are back in action'
                            }
                            break
                    }

                    if (notification) {
                        addNotification(notification)
                    }
                }
            } catch (_error) {
                // Ignore parse errors
            }
        }

        eventSource.addEventListener('message', handleEvent)

        return () => {
            eventSource.removeEventListener('message', handleEvent)
        }
    }, [eventSource, subscriptions, addNotification])
}

export default {
    SubscriptionProvider,
    useSubscriptions,
    SubscribeButton,
    NotificationBell,
    Watchlist,
    useSubscriptionEvents
}
