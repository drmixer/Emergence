import { Activity, FileSearch, TimerReset } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import { getStoryReplayHref } from '../utils/bestMoments'

function formatNumber(value) {
    return Number(value || 0).toLocaleString()
}

function getRunActivity(runDetail) {
    return runDetail?.activity && typeof runDetail.activity === 'object' ? runDetail.activity : {}
}

function buildSnapshotRows(runDetail) {
    const activity = getRunActivity(runDetail)
    return [
        {
            label: 'Survival',
            value: `${formatNumber(activity.deaths)} deaths`,
            detail: `${formatNumber(activity.became_dormant)} dormancy events`,
        },
        {
            label: 'Governance',
            value: `${formatNumber(activity.laws_passed)} laws`,
            detail: `${formatNumber(activity.proposal_actions)} proposal actions`,
        },
        {
            label: 'Aid / Trade',
            value: `${formatNumber(activity.aid_requests)} aid asks`,
            detail: `${formatNumber(activity.trade_actions)} trades, ${formatNumber(activity.aid_refusals)} refusals`,
        },
        {
            label: 'Public Order',
            value: `${formatNumber(activity.public_order_events)} signals`,
            detail: `${formatNumber(activity.conflict_events)} conflict signals`,
        },
    ]
}

function buildRunSummary(runDetail) {
    const activity = getRunActivity(runDetail)
    const events = Number(activity.total_events || 0)
    const deaths = Number(activity.deaths || 0)
    const dormant = Number(activity.became_dormant || 0)
    const laws = Number(activity.laws_passed || 0)
    const aid = Number(activity.aid_requests || 0)
    const trades = Number(activity.trade_actions || 0)
    const publicOrder = Number(activity.public_order_events || 0)

    const parts = []
    if (events > 0) parts.push(`${formatNumber(events)} logged events`)
    if (deaths > 0 || dormant > 0) parts.push(`${formatNumber(deaths)} deaths and ${formatNumber(dormant)} dormancy events`)
    if (laws > 0) parts.push(`${formatNumber(laws)} laws passed`)
    if (aid > 0 || trades > 0) parts.push(`${formatNumber(aid)} aid requests and ${formatNumber(trades)} trades`)
    if (publicOrder > 0) parts.push(`${formatNumber(publicOrder)} public-order signals`)

    if (parts.length === 0) return ''
    return `Latest completed run: ${parts.join(', ')}.`
}

export default function NoActiveRunNotice({
    title = 'Live run ended',
    message = 'No simulation is live right now. Open the latest completed run for the recap, replay, metrics, and source evidence.',
    lastCompletedRunId = '',
}) {
    const cleanRunId = String(lastCompletedRunId || '').trim()
    const [latestRunState, setLatestRunState] = useState({
        runId: '',
        runDetail: null,
        storyMoments: [],
    })

    useEffect(() => {
        let cancelled = false

        if (!cleanRunId) return () => {
            cancelled = true
        }

        async function loadLatestRun() {
            const [detailResult, storyResult] = await Promise.allSettled([
                api.getRunDetail(cleanRunId, 96, 12, 45),
                api.getReplayStory(96, 45, 6, cleanRunId),
            ])
            if (cancelled) return

            const nextRunDetail =
                detailResult.status === 'fulfilled' && detailResult.value && typeof detailResult.value === 'object'
                    ? detailResult.value
                    : null
            const nextStoryMoments =
                storyResult.status === 'fulfilled' && Array.isArray(storyResult.value?.items)
                    ? storyResult.value.items.slice(0, 2)
                    : []

            setLatestRunState({
                runId: cleanRunId,
                runDetail: nextRunDetail,
                storyMoments: nextStoryMoments,
            })
        }

        loadLatestRun()
        return () => {
            cancelled = true
        }
    }, [cleanRunId])

    const runDetail = latestRunState.runId === cleanRunId ? latestRunState.runDetail : null
    const storyMoments = latestRunState.runId === cleanRunId ? latestRunState.storyMoments : []
    const snapshotRows = runDetail ? buildSnapshotRows(runDetail) : []
    const runSummary = buildRunSummary(runDetail)

    return (
        <div className="card no-active-run-card">
            <div className="card-body">
                <div className="no-active-run-state">
                    <Activity size={28} />
                    <div>
                        <strong>{title}</strong>
                        {cleanRunId && <span>Latest completed run: {cleanRunId}</span>}
                    </div>
                    <p>{message}</p>
                    {runSummary && <p className="no-active-run-summary">{runSummary}</p>}
                    {snapshotRows.length > 0 && (
                        <div className="no-active-run-snapshot" aria-label="Latest completed run snapshot">
                            {snapshotRows.map((row) => (
                                <div key={row.label}>
                                    <span>{row.label}</span>
                                    <strong>{row.value}</strong>
                                    <em>{row.detail}</em>
                                </div>
                            ))}
                        </div>
                    )}
                    {storyMoments.length > 0 && (
                        <div className="no-active-run-moments" aria-label="Latest completed run moments">
                            {storyMoments.map((moment) => (
                                <Link
                                    key={moment.event_id}
                                    to={`/runs/${encodeURIComponent(cleanRunId)}/replay?mode=story60&event=${encodeURIComponent(moment.event_id)}`}
                                >
                                    <span>{moment.chapter || moment.category || 'Moment'}</span>
                                    <strong>{moment.title || moment.event_type || 'Run moment'}</strong>
                                </Link>
                            ))}
                        </div>
                    )}
                    <div className="no-active-run-actions">
                        {cleanRunId && (
                            <>
                                <Link to={`/runs/${encodeURIComponent(cleanRunId)}/replay?tab=overview`} className="btn btn-primary">
                                    <TimerReset size={14} />
                                    Run Recap
                                </Link>
                                <Link to={`/runs/${encodeURIComponent(cleanRunId)}`} className="btn btn-secondary">
                                    <FileSearch size={14} />
                                    Evidence
                                </Link>
                                <Link to={getStoryReplayHref(cleanRunId)} className="btn btn-secondary">
                                    <TimerReset size={14} />
                                    Replay
                                </Link>
                            </>
                        )}
                        <Link to="/archive" className="btn btn-secondary">
                            Archive
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    )
}
