// Keyboard Navigation hook for accessibility
import { useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

// Hook to add keyboard navigation to the app
export function useKeyboardNavigation() {
    const navigate = useNavigate()

    const handleKeyDown = useCallback((event) => {
        // Don't interfere with input fields
        if (
            event.target.tagName === 'INPUT' ||
            event.target.tagName === 'TEXTAREA' ||
            event.target.isContentEditable
        ) {
            return
        }

        // Global keyboard shortcuts
        switch (event.key) {
            case 'Escape': {
                // Close any open modals/overlays
                const overlay = document.querySelector('.mobile-nav-overlay')
                if (overlay) {
                    overlay.click()
                }
                break
            }

            case 'g':
                // Go shortcuts with modifier
                if (event.ctrlKey || event.metaKey) {
                    event.preventDefault()
                    // Show navigation hint (could add a command palette here)
                }
                break

            case '1':
                if (event.altKey) {
                    event.preventDefault()
                    navigate('/dashboard')
                }
                break

            case '2':
                if (event.altKey) {
                    event.preventDefault()
                    navigate('/agents')
                }
                break

            case '3':
                if (event.altKey) {
                    event.preventDefault()
                    navigate('/proposals')
                }
                break

            case '4':
                if (event.altKey) {
                    event.preventDefault()
                    navigate('/laws')
                }
                break

            case '/': {
                // Focus search (if we add one)
                const searchInput = document.querySelector('.search-input')
                if (searchInput) {
                    event.preventDefault()
                    searchInput.focus()
                }
                break
            }

            default:
                break
        }
    }, [navigate])

    useEffect(() => {
        document.addEventListener('keydown', handleKeyDown)
        return () => document.removeEventListener('keydown', handleKeyDown)
    }, [handleKeyDown])
}

// Hook to make a list of items keyboard navigable
export function useListKeyboardNavigation(
    containerRef,
    itemSelector = '[data-focusable]',
    onSelect = null
) {
    const handleKeyDown = useCallback((event) => {
        if (!containerRef.current) return

        const items = containerRef.current.querySelectorAll(itemSelector)
        if (items.length === 0) return

        const currentIndex = Array.from(items).findIndex(
            item => item === document.activeElement
        )

        switch (event.key) {
            case 'ArrowDown':
            case 'j': {
                event.preventDefault()
                const nextIndex = currentIndex < items.length - 1 ? currentIndex + 1 : 0
                items[nextIndex]?.focus()
                break
            }

            case 'ArrowUp':
            case 'k': {
                event.preventDefault()
                const prevIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1
                items[prevIndex]?.focus()
                break
            }

            case 'Enter':
            case ' ':
                if (document.activeElement && onSelect) {
                    event.preventDefault()
                    onSelect(document.activeElement)
                }
                break

            case 'Home':
                event.preventDefault()
                items[0]?.focus()
                break

            case 'End':
                event.preventDefault()
                items[items.length - 1]?.focus()
                break

            default:
                break
        }
    }, [containerRef, itemSelector, onSelect])

    useEffect(() => {
        const container = containerRef.current
        if (!container) return

        container.addEventListener('keydown', handleKeyDown)
        return () => container.removeEventListener('keydown', handleKeyDown)
    }, [containerRef, handleKeyDown])
}

// Component to wrap focusable cards
export function FocusableCard({ children, onClick, className = '', ...props }) {
    return (
        <div
            className={`focusable-card ${className}`}
            tabIndex={0}
            role="button"
            data-focusable
            onClick={onClick}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onClick?.()
                }
            }}
            {...props}
        >
            {children}
        </div>
    )
}

// Keyboard shortcuts help tooltip
export function KeyboardShortcutsHelp() {
    return (
        <div className="keyboard-shortcuts-help">
            <h4>Keyboard Shortcuts</h4>
            <ul>
                <li><kbd>Alt</kbd> + <kbd>1-4</kbd> - Navigate pages</li>
                <li><kbd>/</kbd> - Focus search</li>
                <li><kbd>Esc</kbd> - Close menus</li>
                <li><kbd>↑</kbd>/<kbd>↓</kbd> or <kbd>j</kbd>/<kbd>k</kbd> - Navigate lists</li>
                <li><kbd>Enter</kbd> - Select item</li>
            </ul>

            <style>{`
                .keyboard-shortcuts-help {
                    padding: 16px;
                    background: var(--bg-card);
                    border: 1px solid var(--border-color);
                    border-radius: var(--radius-lg);
                    font-size: 0.875rem;
                }
                
                .keyboard-shortcuts-help h4 {
                    margin-bottom: 12px;
                    font-size: 0.875rem;
                    font-weight: 600;
                }
                
                .keyboard-shortcuts-help ul {
                    list-style: none;
                    padding: 0;
                    margin: 0;
                }
                
                .keyboard-shortcuts-help li {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    padding: 6px 0;
                    color: var(--text-secondary);
                }
                
                .keyboard-shortcuts-help kbd {
                    display: inline-block;
                    padding: 2px 6px;
                    background: var(--bg-tertiary);
                    border: 1px solid var(--border-color);
                    border-radius: 4px;
                    font-family: var(--font-mono);
                    font-size: 0.75rem;
                    color: var(--text-primary);
                }
                
                .focusable-card:focus {
                    outline: 2px solid var(--accent-blue);
                    outline-offset: 2px;
                }
                
                .focusable-card:focus-visible {
                    outline: 2px solid var(--accent-blue);
                    outline-offset: 2px;
                }
            `}</style>
        </div>
    )
}

export default useKeyboardNavigation
