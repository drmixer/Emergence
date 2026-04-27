import { Activity, FileSearch, TimerReset } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getStoryReplayHref } from '../utils/bestMoments'

export default function NoActiveRunNotice({
    title = 'No run in progress',
    message = 'This live surface will update when the next simulation starts. Review completed evidence in the archive for the last run.',
    lastCompletedRunId = '',
}) {
    const cleanRunId = String(lastCompletedRunId || '').trim()

    return (
        <div className="card no-active-run-card">
            <div className="card-body">
                <div className="no-active-run-state">
                    <Activity size={28} />
                    <div>
                        <strong>{title}</strong>
                    </div>
                    <p>{message}</p>
                    <div className="no-active-run-actions">
                        {cleanRunId && (
                            <>
                                <Link to={`/runs/${encodeURIComponent(cleanRunId)}`} className="btn btn-primary">
                                    <FileSearch size={14} />
                                    Latest Evidence
                                </Link>
                                <Link to={getStoryReplayHref(cleanRunId)} className="btn btn-secondary">
                                    <TimerReset size={14} />
                                    Replay Latest Run
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
