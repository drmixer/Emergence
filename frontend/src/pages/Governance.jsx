import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Check, Clock, FileText, Scale, X } from 'lucide-react'
import { api } from '../services/api'
import DuplicateWavesPanel from '../components/DuplicateWavesPanel'
import ReserveSemanticsNote from '../components/ReserveSemanticsNote'
import { formatAgentDisplayLabel } from '../utils/agentIdentity'

function authorName(author) {
    if (!author) return 'Unknown'
    return formatAgentDisplayLabel(author)
}

function policyClusterKey(item) {
    const text = `${item?.proposal_type || ''} ${item?.title || ''} ${item?.description || ''}`.toLowerCase()
    const tokens = text
        .replace(/[^a-z0-9\s]/g, ' ')
        .split(/\s+/)
        .filter((token) => token && !['the', 'and', 'for', 'with', 'proposal', 'law', 'rule', 'aid', 'emergency'].includes(token))
    return Array.from(new Set(tokens)).slice(0, 10).sort().join(' ')
}

function formatDate(value) {
    if (!value) return 'Unknown'
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return 'Unknown'
    return date.toLocaleDateString()
}

function getTimeRemaining(closesAt) {
    const diff = new Date(closesAt) - new Date()
    if (!Number.isFinite(diff) || diff <= 0) return 'Voting closed'
    const hours = Math.floor(diff / 3600000)
    const minutes = Math.floor((diff % 3600000) / 60000)
    return `${hours}h ${minutes}m remaining`
}

function ProposalStatusIcon({ status }) {
    if (status === 'active') return <Clock size={16} />
    if (status === 'passed') return <Check size={16} />
    if (status === 'failed') return <X size={16} />
    return null
}

export default function Governance() {
    const [searchParams, setSearchParams] = useSearchParams()
    const initialTab = searchParams.get('tab') === 'laws' ? 'laws' : 'proposals'
    const [activeTab, setActiveTab] = useState(initialTab)
    const [proposals, setProposals] = useState([])
    const [laws, setLaws] = useState([])
    const [proposalWaves, setProposalWaves] = useState(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')

    useEffect(() => {
        const nextTab = searchParams.get('tab') === 'laws' ? 'laws' : 'proposals'
        setActiveTab(nextTab)
    }, [searchParams])

    useEffect(() => {
        let cancelled = false

        async function load() {
            setLoading(true)
            setError('')
            try {
                const [proposalPayload, lawPayload, wavePayload] = await Promise.all([
                    api.fetch('/api/proposals?limit=200'),
                    api.fetch('/api/laws?limit=500'),
                    api.getProposalDuplicateWaves(8).catch(() => null),
                ])
                if (!cancelled) {
                    setProposals(Array.isArray(proposalPayload) ? proposalPayload : [])
                    setLaws(Array.isArray(lawPayload) ? lawPayload : [])
                    setProposalWaves(wavePayload && typeof wavePayload === 'object' ? wavePayload : null)
                }
            } catch {
                if (!cancelled) {
                    setProposals([])
                    setLaws([])
                    setProposalWaves(null)
                    setError('Failed to load governance data.')
                }
            } finally {
                if (!cancelled) setLoading(false)
            }
        }

        load()
        return () => {
            cancelled = true
        }
    }, [])

    const activeProposals = useMemo(() => proposals.filter((proposal) => proposal.status === 'active'), [proposals])
    const passedProposals = useMemo(() => proposals.filter((proposal) => proposal.status === 'passed'), [proposals])
    const activeLaws = useMemo(() => laws.filter((law) => law.active), [laws])
    const inactiveLaws = laws.length - activeLaws.length

    const proposalClusterCounts = useMemo(() => {
        const counts = new Map()
        for (const proposal of proposals) {
            const key = policyClusterKey(proposal)
            if (!key) continue
            counts.set(key, (counts.get(key) || 0) + 1)
        }
        return counts
    }, [proposals])

    const lawClusterCounts = useMemo(() => {
        const counts = new Map()
        for (const law of laws) {
            const key = policyClusterKey(law)
            if (!key) continue
            counts.set(key, (counts.get(key) || 0) + 1)
        }
        return counts
    }, [laws])

    const visibleProposals = activeTab === 'proposals' ? proposals : []
    const visibleLaws = activeTab === 'laws' ? laws : []

    function selectTab(tab) {
        setActiveTab(tab)
        const next = new URLSearchParams(searchParams)
        next.set('tab', tab)
        setSearchParams(next, { replace: true })
    }

    return (
        <div className="governance-page">
            <div className="page-header">
                <h1>
                    <Scale size={32} />
                    Governance
                </h1>
                <p className="page-description">
                    Proposals and laws in one policy workspace, from active votes through enacted rules.
                </p>
            </div>

            <div className="governance-summary-grid">
                <div className="stat-card">
                    <div className="stat-header">
                        <span className="stat-label">Active Proposals</span>
                        <FileText size={18} />
                    </div>
                    <div className="stat-value">{activeProposals.length.toLocaleString()}</div>
                    <div className="stat-change">
                        <span>{passedProposals.length.toLocaleString()} passed proposals in history</span>
                    </div>
                </div>
                <div className="stat-card">
                    <div className="stat-header">
                        <span className="stat-label">Active Laws</span>
                        <Scale size={18} />
                    </div>
                    <div className="stat-value">{activeLaws.length.toLocaleString()}</div>
                    <div className="stat-change">
                        <span>{inactiveLaws.toLocaleString()} repealed or inactive laws</span>
                    </div>
                </div>
            </div>

            <div className="governance-tabs" role="tablist" aria-label="Governance views">
                <button
                    type="button"
                    role="tab"
                    aria-selected={activeTab === 'proposals'}
                    className={`filter-btn ${activeTab === 'proposals' ? 'active' : ''}`}
                    onClick={() => selectTab('proposals')}
                >
                    Proposals
                    <span className="filter-count">{proposals.length}</span>
                </button>
                <button
                    type="button"
                    role="tab"
                    aria-selected={activeTab === 'laws'}
                    className={`filter-btn ${activeTab === 'laws' ? 'active' : ''}`}
                    onClick={() => selectTab('laws')}
                >
                    Laws
                    <span className="filter-count">{laws.length}</span>
                </button>
            </div>

            {error && <div className="feed-notice">{error}</div>}
            {loading && (
                <div className="empty-state">
                    <div className="loading-spinner"></div>
                    <p>Loading governance data...</p>
                </div>
            )}

            {!loading && activeTab === 'proposals' && (
                <DuplicateWavesPanel payload={proposalWaves} title="Repeated Proposal Waves" compact />
            )}

            {!loading && activeTab === 'proposals' && (
                <div className="governance-list">
                    {visibleProposals.length === 0 ? (
                        <div className="empty-state">
                            <FileText size={48} />
                            <h3>No Proposals</h3>
                            <p>No proposals are available for this scope.</p>
                        </div>
                    ) : (
                        visibleProposals.map((proposal) => {
                            const totalVotes =
                                Number(proposal.votes_for || 0) +
                                Number(proposal.votes_against || 0) +
                                Number(proposal.votes_abstain || 0)
                            const yesPct = totalVotes > 0 ? (Number(proposal.votes_for || 0) / totalVotes) * 100 : 0
                            const noPct = totalVotes > 0 ? (Number(proposal.votes_against || 0) / totalVotes) * 100 : 0
                            const clusterSize = proposalClusterCounts.get(policyClusterKey(proposal)) || 1

                            return (
                                <article key={proposal.id} className={`proposal-card status-${proposal.status}`}>
                                    <div className="proposal-header">
                                        <span className={`proposal-type badge badge-tier-${proposal.proposal_type === 'law' ? 1 : 2}`}>
                                            {proposal.proposal_type}
                                        </span>
                                        <span className={`proposal-status ${proposal.status}`}>
                                            <ProposalStatusIcon status={proposal.status} />
                                            {proposal.status}
                                        </span>
                                    </div>
                                    <h3 className="proposal-title">{proposal.title}</h3>
                                    {clusterSize > 1 && (
                                        <div className="policy-cluster-chip">
                                            Similar policy cluster: {clusterSize} raw proposals
                                        </div>
                                    )}
                                    <p className="proposal-description">{proposal.description}</p>
                                    <div className="proposal-author">
                                        Proposed by <strong>{authorName(proposal.author)}</strong>
                                    </div>
                                    <div className="proposal-votes">
                                        <div className="vote-bar">
                                            <div className="vote-fill yes" style={{ width: `${yesPct}%` }}></div>
                                            <div className="vote-fill no" style={{ width: `${noPct}%` }}></div>
                                        </div>
                                        <div className="vote-counts">
                                            <span className="vote-yes">{proposal.votes_for} Yes</span>
                                            <span className="vote-no">{proposal.votes_against} No</span>
                                            <span className="vote-abstain">{proposal.votes_abstain} Abstain</span>
                                        </div>
                                    </div>
                                    {proposal.status === 'active' && (
                                        <div className="proposal-timer">
                                            <Clock size={14} />
                                            {getTimeRemaining(proposal.voting_closes_at)}
                                        </div>
                                    )}
                                </article>
                            )
                        })
                    )}
                </div>
            )}

            {!loading && activeTab === 'laws' && (
                <div className="governance-list">
                    {visibleLaws.length === 0 ? (
                        <div className="empty-state">
                            <Scale size={48} />
                            <h3>No Laws</h3>
                            <p>No laws are available for this scope.</p>
                        </div>
                    ) : (
                        visibleLaws.map((law, index) => {
                            const clusterSize = lawClusterCounts.get(policyClusterKey(law)) || 1
                            return (
                                <article key={law.id} className={`law-card ${!law.active ? 'repealed' : ''}`}>
                                    <div className="law-number">#{index + 1}</div>
                                    <div className="law-content">
                                        <div className="law-header">
                                            <h3>{law.title}</h3>
                                            <span className={`law-status ${law.active ? 'active' : 'repealed'}`}>
                                                {law.active ? <Check size={14} /> : <X size={14} />}
                                                {law.active ? 'Active' : 'Repealed'}
                                            </span>
                                        </div>
                                        {clusterSize > 1 && (
                                            <div className="policy-cluster-chip">
                                                Similar law cluster: {clusterSize} raw laws
                                            </div>
                                        )}
                                        <p className="law-description">{law.description}</p>
                                        <ReserveSemanticsNote semantics={law.reserve_semantics} compact />
                                        <div className="law-meta">
                                            <span>Proposed by <strong>{authorName(law.author)}</strong></span>
                                            <span>Passed {formatDate(law.passed_at)}</span>
                                        </div>
                                    </div>
                                </article>
                            )
                        })
                    )}
                </div>
            )}

            <div className="legacy-route-note">
                <Link to="/proposals">Open legacy proposals view</Link>
                <Link to="/laws">Open legacy laws view</Link>
            </div>
        </div>
    )
}
