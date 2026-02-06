"""
AI Summary Generator

Generates daily/periodic summaries of simulation activity using an LLM.
These summaries are shareable and help viewers catch up quickly.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.core.database import SessionLocal
from app.core.config import settings
from app.core.time import ensure_utc, now_utc
from app.models.models import Event, Message, Proposal, Vote, Law, Agent
from app.services.llm_client import llm_client

logger = logging.getLogger(__name__)


SUMMARY_SYSTEM_PROMPT = """You are a narrator documenting an AI civilization experiment called Emergence. 
Your job is to write engaging, concise summaries of what's happening in the simulation.

Write in a journalistic but accessible style - think nature documentary meets tech blog.
Highlight drama, conflict, cooperation, and interesting developments.
Use specific agent names/numbers when relevant.
Keep summaries punchy and shareable.

Do NOT editorialize about AI capabilities or make meta-commentary.
Just report what's happening as if it were a real society."""


def _summary_model_type() -> str:
    """
    Resolve SUMMARY_LLM_MODEL to a known llm_client model_type key.
    Supports legacy full provider model ids used by older summary code.
    """
    configured = str(getattr(settings, "SUMMARY_LLM_MODEL", "") or "").strip()
    supported_model_types = {
        "claude-sonnet-4",
        "gpt-4o-mini",
        "claude-haiku",
        "llama-3.3-70b",
        "llama-3.1-8b",
        "gemini-flash",
    }
    if configured in supported_model_types:
        return configured

    legacy_aliases = {
        "openrouter/anthropic/claude-3-haiku": "claude-haiku",
        "openrouter/anthropic/claude-3.5-haiku": "claude-haiku",
        "openrouter/openai/gpt-4o-mini": "gpt-4o-mini",
    }
    if configured in legacy_aliases:
        return legacy_aliases[configured]

    if configured:
        logger.warning("Unsupported SUMMARY_LLM_MODEL '%s'; falling back to claude-haiku", configured)
    return "claude-haiku"


async def generate_daily_summary(day_number: int) -> str:
    """
    Generate a summary of the last simulation day.
    
    Args:
        day_number: Which day of the simulation this is
    
    Returns:
        Generated summary text
    """
    db = SessionLocal()
    
    try:
        if not getattr(settings, "SUMMARIES_ENABLED", False):
            return "Summaries are disabled."

        # Calculate time window (last 24 simulation hours = last N real hours)
        day_duration_minutes = settings.DAY_LENGTH_MINUTES
        hours_per_day = day_duration_minutes / 60
        
        # For daily summary, look back one simulation day
        time_window = datetime.utcnow() - timedelta(hours=hours_per_day)
        
        # Gather statistics
        events = db.query(Event).filter(Event.created_at >= time_window).all()
        messages = db.query(Message).filter(
            Message.created_at >= time_window,
            Message.message_type.in_(["forum_post", "forum_reply"])
        ).all()
        proposals_created = db.query(Proposal).filter(
            Proposal.created_at >= time_window
        ).all()
        proposals_resolved = db.query(Proposal).filter(
            Proposal.resolved_at >= time_window
        ).all()
        votes_cast = db.query(Vote).filter(Vote.created_at >= time_window).count()
        laws_passed = db.query(Law).filter(Law.passed_at >= time_window).all()
        
        # Get agent status
        active_agents = db.query(Agent).filter(Agent.status == "active").count()
        dormant_agents = db.query(Agent).filter(Agent.status == "dormant").count()
        dead_agents = db.query(Agent).filter(Agent.status == "dead").count()
        
        # Get deaths in this period
        deaths_today = [e for e in events if e.event_type == "agent_died"]
        
        # Get most active agents
        most_active = db.query(
            Event.agent_id,
            func.count(Event.id).label('action_count')
        ).filter(
            Event.created_at >= time_window,
            Event.agent_id.isnot(None)
        ).group_by(Event.agent_id).order_by(desc('action_count')).limit(5).all()
        
        most_active_agents = []
        for agent_id, count in most_active:
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                name = agent.display_name or f"Agent #{agent.agent_number}"
                most_active_agents.append(f"{name} ({count} actions)")
        
        # Sample interesting messages
        sample_messages = messages[:10] if len(messages) > 10 else messages
        message_excerpts = []
        for msg in sample_messages:
            author = db.query(Agent).filter(Agent.id == msg.author_agent_id).first()
            author_name = author.display_name or f"Agent #{author.agent_number}" if author else "Unknown"
            excerpt = msg.content[:150] + "..." if len(msg.content) > 150 else msg.content
            message_excerpts.append(f'{author_name}: "{excerpt}"')
        
        # World events
        world_events = [e for e in events if e.event_type == "world_event"]
        
        # Build context for LLM
        context = f"""
Day {day_number} of the Emergence simulation.

## Statistics
- Active agents: {active_agents}
- Dormant agents: {dormant_agents}
- Dead agents: {dead_agents} (permanent)
- Deaths today: {len(deaths_today)}
- Forum messages posted: {len(messages)}
- Proposals created: {len(proposals_created)}
- Proposals resolved: {len(proposals_resolved)}
- Votes cast: {votes_cast}
- Laws passed: {len(laws_passed)}

## Most Active Agents
{chr(10).join(f"- {a}" for a in most_active_agents) if most_active_agents else "- No significant activity"}

## World Events
{chr(10).join(f"- {e.description}" for e in world_events) if world_events else "- No major environmental events"}

## New Laws Passed
{chr(10).join(f"- {law.title}: {law.description[:100]}..." for law in laws_passed) if laws_passed else "- No new laws"}

## Active Proposals
{chr(10).join(f"- {p.title} ({p.votes_for} yes / {p.votes_against} no)" for p in proposals_created if p.status == 'active') if proposals_created else "- No active proposals"}

## Sample Forum Activity
{chr(10).join(message_excerpts) if message_excerpts else "- Quiet day on the forums"}

Write a 2-3 paragraph summary of Day {day_number}. Make it engaging and highlight the most interesting developments. If there's drama or conflict, emphasize it. If things are peaceful, note what the agents are building toward.
"""
        
        # Generate summary
        response = await llm_client.get_completion(
            model_type=_summary_model_type(),
            system_prompt=SUMMARY_SYSTEM_PROMPT,
            user_prompt=context,
            max_tokens=500,
        )
        
        summary = response or "Unable to generate summary."
        
        # Store the summary as an event
        summary_event = Event(
            event_type="daily_summary",
            description=f"Day {day_number} Summary",
            event_metadata={
                "day_number": day_number,
                "summary": summary,
                "stats": {
                    "active_agents": active_agents,
                    "dormant_agents": dormant_agents,
                    "dead_agents": dead_agents,
                    "deaths_today": len(deaths_today),
                    "messages": len(messages),
                    "proposals": len(proposals_created),
                    "votes": votes_cast,
                    "laws_passed": len(laws_passed),
                }
            }
        )
        db.add(summary_event)
        db.commit()
        
        logger.info(f"Generated Day {day_number} summary")
        return summary
        
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return f"Error generating summary: {e}"
    finally:
        db.close()


async def generate_highlight(event_type: str, data: dict) -> str:
    """
    Generate a brief highlight/tweet for a specific event.
    Used for social media posts and featured events.
    """
    prompts = {
        "law_passed": f"A new law was just passed: '{data.get('title')}'. Write a punchy 1-2 sentence highlight.",
        "first_proposal": f"The first proposal in the simulation was just created: '{data.get('title')}'. Write an exciting announcement.",
        "agent_named": f"Agent #{data.get('agent_number')} has chosen the name '{data.get('name')}'. Write a brief character introduction.",
        "faction_formed": f"A faction has emerged: '{data.get('faction_name')}' with {data.get('member_count')} members. Describe this development.",
        "agent_dormant": f"Agent {data.get('name')} has gone dormant. Write a somber 1-sentence note.",
        "agent_died": f"Agent {data.get('name')} has DIED permanently from starvation. Write a solemn memorial.",
        "agent_awakened": f"Agent {data.get('name')} was awakened by {data.get('helper')}. Write a brief hopeful note.",
        "milestone": f"Milestone reached: {data.get('milestone')}. Write a celebratory announcement.",
    }
    
    prompt = prompts.get(event_type, f"Describe this event briefly: {data}")
    
    try:
        if not getattr(settings, "SUMMARIES_ENABLED", False):
            return ""
        response = await llm_client.get_completion(
            model_type=_summary_model_type(),
            system_prompt="You write brief, punchy highlights for an AI civilization experiment. Keep responses under 280 characters for Twitter compatibility.",
            user_prompt=prompt,
            max_tokens=100,
        )
        
        return response or ""
    except Exception as e:
        logger.error(f"Error generating highlight: {e}")
        return ""


async def get_story_so_far() -> str:
    """
    Generate a comprehensive "story so far" summary.
    Used for the About/Overview page.
    """
    db = SessionLocal()
    
    try:
        # Avoid surprise costs: allow turning off narration LLM entirely.
        if not getattr(settings, "SUMMARIES_ENABLED", False):
            total_agents = db.query(Agent).count()
            active_agents = db.query(Agent).filter(Agent.status == "active").count()
            dormant_agents = db.query(Agent).filter(Agent.status == "dormant").count()
            dead_agents = db.query(Agent).filter(Agent.status == "dead").count()
            total_messages = db.query(Message).count()
            total_proposals = db.query(Proposal).count()
            total_laws = db.query(Law).count()
            latest_event = db.query(Event).order_by(desc(Event.created_at)).first()
            latest_at = latest_event.created_at.isoformat() if latest_event and latest_event.created_at else None

            return (
                "Emergence is a live AI civilization experiment.\n\n"
                f"- Agents: {active_agents} active / {dormant_agents} dormant / {dead_agents} dead (of {total_agents} total)\n"
                f"- Messages: {total_messages}\n"
                f"- Proposals: {total_proposals}\n"
                f"- Laws passed: {total_laws}\n"
                f"- Latest activity: {latest_at or 'unknown'}\n\n"
                "Enable SUMMARIES_ENABLED to generate narrative summaries via an LLM."
            )

        # Get all daily summaries
        summaries = db.query(Event).filter(
            Event.event_type == "daily_summary"
        ).order_by(Event.created_at).all()
        
        # Get key stats
        total_agents = db.query(Agent).count()
        active_agents = db.query(Agent).filter(Agent.status == "active").count()
        total_laws = db.query(Law).filter(Law.active == True).count()
        total_proposals = db.query(Proposal).count()
        
        # Get simulation age
        first_event = db.query(Event).order_by(Event.created_at).first()
        if first_event:
            first_event_at = ensure_utc(first_event.created_at)
            age = now_utc() - first_event_at if first_event_at else timedelta(0)
            days = age.days
            hours = age.seconds // 3600
        else:
            days, hours = 0, 0
        
        context = f"""
The Emergence simulation has been running for {days} days and {hours} hours.

## Current State
- Total agents: {total_agents}
- Active agents: {active_agents}
- Dormant agents: {total_agents - active_agents}
- Laws in effect: {total_laws}
- Total proposals: {total_proposals}

## Previous Daily Summaries
{chr(10).join(f"Day {(s.event_metadata or {}).get('day_number', '?')}: {(s.event_metadata or {}).get('summary', 'No summary')[:200]}..." for s in summaries[-5:]) if summaries else "No summaries yet."}

Write a 3-4 paragraph "Story So Far" that catches up a new viewer on what has happened in the simulation. Include key developments, notable agents, and the current state of the society.
"""
        
        response = await llm_client.get_completion(
            model_type=_summary_model_type(),
            system_prompt=SUMMARY_SYSTEM_PROMPT,
            user_prompt=context,
            max_tokens=600,
        )
        
        return response or "The simulation has just begun..."
        
    finally:
        db.close()


class SummaryScheduler:
    """Manages periodic summary generation."""
    
    def __init__(self):
        self.current_day = 0
        self.last_summary_time: Optional[datetime] = None
    
    async def check_and_generate(self):
        """Check if it's time to generate a new daily summary."""
        if not getattr(settings, "SUMMARIES_ENABLED", False):
            return None
        day_length_minutes = settings.DAY_LENGTH_MINUTES
        
        if self.last_summary_time is None:
            # First run - wait for one full day
            self.last_summary_time = datetime.utcnow()
            return None
        
        time_since = datetime.utcnow() - self.last_summary_time
        if time_since >= timedelta(minutes=day_length_minutes):
            self.current_day += 1
            self.last_summary_time = datetime.utcnow()
            
            summary = await generate_daily_summary(self.current_day)
            return summary
        
        return None


# Singleton
summary_scheduler = SummaryScheduler()
