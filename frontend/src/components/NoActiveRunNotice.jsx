import { Activity, CalendarDays, Eye, FileSearch, FileText, TimerReset } from 'lucide-react'
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

function hasViewerBriefReport(reportsPayload) {
    const items = Array.isArray(reportsPayload?.items) ? reportsPayload.items : []
    return items.some((item) => (
        String(item?.artifact_type || '').trim() === 'viewer_brief'
        && String(item?.artifact_format || '').trim() === 'markdown'
        && String(item?.status || '').trim() === 'completed'
    ))
}

export default function NoActiveRunNotice({
    title = 'Live run ended',
    message = 'No simulation is live right now. Open the latest completed run for the recap, replay, metrics, and source evidence.',
    lastCompletedRunId = '',
    showCompletedRunHandoff = true,
    handoffMode = 'rich',
    chrome = 'card',
}) {
    const cleanRunId = String(lastCompletedRunId || '').trim()
    const richHandoff = handoffMode !== 'ops'
    const [latestRunState, setLatestRunState] = useState({
        runId: '',
        runDetail: null,
        storyMoments: [],
        hasViewerBrief: false,
    })

    useEffect(() => {
        let cancelled = false

        if (!cleanRunId || !showCompletedRunHandoff || !richHandoff) return () => {
            cancelled = true
        }

        async function loadLatestRun() {
            const [detailResult, storyResult, reportsResult] = await Promise.allSettled([
                api.getRunDetail(cleanRunId, 96, 12, 45),
                api.getReplayStory(96, 45, 6, cleanRunId),
                typeof api.getRunReports === 'function' ? api.getRunReports(cleanRunId) : Promise.resolve(null),
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
            const nextHasViewerBrief =
                reportsResult.status === 'fulfilled'
                && hasViewerBriefReport(reportsResult.value)

            setLatestRunState({
                runId: cleanRunId,
                runDetail: nextRunDetail,
                storyMoments: nextStoryMoments,
                hasViewerBrief: nextHasViewerBrief,
            })
        }

        loadLatestRun()
        return () => {
            cancelled = true
        }
    }, [cleanRunId, showCompletedRunHandoff, richHandoff])

    const runDetail = latestRunState.runId === cleanRunId ? latestRunState.runDetail : null
    const storyMoments = latestRunState.runId === cleanRunId ? latestRunState.storyMoments : []
    const hasViewerBrief = latestRunState.runId === cleanRunId && latestRunState.hasViewerBrief
    const snapshotRows = runDetail ? buildSnapshotRows(runDetail) : []
    const runSummary = buildRunSummary(runDetail)
    const viewerBriefHref = cleanRunId
        ? `/runs/${encodeURIComponent(cleanRunId)}/reports/viewer_brief?format=markdown`
        : ''
    const rootClassName = `${chrome === 'inline'
        ? 'no-active-run-card no-active-run-inline'
        : 'card no-active-run-card'} ${richHandoff ? 'no-active-run-rich' : 'no-active-run-ops'}`

    return (
        <div className={rootClassName}>
            <div className="card-body">
                <div className="no-active-run-state">
                    <Activity size={28} />
                    <div>
                        <strong>{title}</strong>
                        {showCompletedRunHandoff && cleanRunId && <span>Latest completed run: {cleanRunId}</span>}
                    </div>
                    <p>{message}</p>
                    {showCompletedRunHandoff && richHandoff && runSummary && <p className="no-active-run-summary">{runSummary}</p>}
                    {showCompletedRunHandoff && richHandoff && hasViewerBrief && (
                        <Link className="no-active-run-brief-link" to={viewerBriefHref}>
                            <span>
                                <FileText size={15} />
                                Latest Emergence Brief
                            </span>
                            <strong>Read the news-style recap before the next run starts.</strong>
                        </Link>
                    )}
                    {showCompletedRunHandoff && richHandoff && snapshotRows.length > 0 && (
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
                    {showCompletedRunHandoff && richHandoff && storyMoments.length > 0 && (
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
                        {showCompletedRunHandoff && cleanRunId && (
                            <>
                                {richHandoff ? (
                                    <>
                                        <Link to={hasViewerBrief ? viewerBriefHref : `/runs/${encodeURIComponent(cleanRunId)}/replay?tab=overview`} className="btn btn-primary">
                                            {hasViewerBrief ? <FileText size={14} /> : <TimerReset size={14} />}
                                            {hasViewerBrief ? 'Read Brief' : 'Open Recap'}
                                        </Link>
                                        {hasViewerBrief && (
                                            <Link to={`/runs/${encodeURIComponent(cleanRunId)}/replay?tab=overview`} className="btn btn-secondary">
                                                <TimerReset size={14} />
                                                Open Recap
                                            </Link>
                                        )}
                                    </>
                                ) : (
                                    <Link to={`/watch?run=${encodeURIComponent(cleanRunId)}`} className="btn btn-primary">
                                        <Eye size={14} />
                                        Watch Map
                                    </Link>
                                )}
                                {richHandoff && (
                                    <Link to={`/watch?run=${encodeURIComponent(cleanRunId)}`} className="btn btn-secondary">
                                        <Eye size={14} />
                                        Watch Map
                                    </Link>
                                )}
                                <Link to={getStoryReplayHref(cleanRunId)} className="btn btn-secondary">
                                    <TimerReset size={14} />
                                    Replay
                                </Link>
                                <Link to={`/runs/${encodeURIComponent(cleanRunId)}`} className="btn btn-secondary">
                                    <FileSearch size={14} />
                                    Evidence
                                </Link>
                            </>
                        )}
                        <Link to="/archive" className="btn btn-secondary">
                            <FileSearch size={14} />
                            Archive
                        </Link>
                        <Link to="/calendar" className="btn btn-secondary">
                            <CalendarDays size={14} />
                            Run Calendar
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    )
}
