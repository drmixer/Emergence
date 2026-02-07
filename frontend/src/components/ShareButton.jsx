// Share Button with copy-to-clipboard and social sharing
import { useState } from 'react'
import { Share2, Copy, Check, Twitter, Link as LinkIcon } from 'lucide-react'

export default function ShareButton({
    url,
    title = 'Check out this AI agent',
    description = '',
    variant = 'default' // 'default', 'compact', 'icon-only'
}) {
    const [isOpen, setIsOpen] = useState(false)
    const [copied, setCopied] = useState(false)

    const shareUrl = url || window.location.href

    const copyToClipboard = async () => {
        try {
            await navigator.clipboard.writeText(shareUrl)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        } catch (err) {
            console.error('Failed to copy:', err)
        }
    }

    const shareToTwitter = () => {
        const text = `${title}\n\n${description}`
        const twitterUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(shareUrl)}`
        window.open(twitterUrl, '_blank', 'width=550,height=435')
    }

    const handleNativeShare = async () => {
        if (navigator.share) {
            try {
                await navigator.share({
                    title,
                    text: description,
                    url: shareUrl,
                })
            } catch (err) {
                if (err.name !== 'AbortError') {
                    console.error('Share failed:', err)
                }
            }
        } else {
            setIsOpen(!isOpen)
        }
    }

    if (variant === 'icon-only') {
        return (
            <button
                className="share-button icon-only"
                onClick={handleNativeShare}
                title="Share"
            >
                <Share2 size={18} />
            </button>
        )
    }

    return (
        <div className="share-container">
            <button
                className={`share-button ${variant}`}
                onClick={handleNativeShare}
            >
                <Share2 size={16} />
                {variant !== 'compact' && <span>Share</span>}
            </button>

            {isOpen && (
                <>
                    <div className="share-overlay" onClick={() => setIsOpen(false)} />
                    <div className="share-dropdown">
                        <div className="share-header">Share this page</div>

                        <button className="share-option" onClick={shareToTwitter}>
                            <Twitter size={18} />
                            <span>Share on Twitter</span>
                        </button>

                        <button className="share-option" onClick={copyToClipboard}>
                            {copied ? <Check size={18} /> : <Copy size={18} />}
                            <span>{copied ? 'Copied!' : 'Copy link'}</span>
                        </button>

                        <div className="share-url">
                            <LinkIcon size={14} />
                            <input
                                type="text"
                                value={shareUrl}
                                readOnly
                                onClick={(e) => e.target.select()}
                            />
                        </div>
                    </div>
                </>
            )}
        </div>
    )
}
