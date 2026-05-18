import { Activity, FileSearch, TimerReset } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getStoryReplayHref } from '../utils/bestMoments'

export default function NoActiveRunNotice({
    title = 'Live run ended',
    message = 'No simulation is live right now. Open the latest completed run for the recap, replay, metrics, and source evidence.',
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
                                    Latest Run Details
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
