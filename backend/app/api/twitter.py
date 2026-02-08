"""
Twitter Bot API Endpoints
Monitor and control the Twitter bot
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.core.admin_auth import AdminActor, require_admin_auth

# Twitter bot integration
try:
    from app.services.twitter_bot import (
        twitter_bot, 
        tweet_formatter,
        get_twitter_status,
        TweetType,
        TweetContent
    )
    TWITTER_AVAILABLE = True
except ImportError:
    TWITTER_AVAILABLE = False

router = APIRouter(prefix="/twitter", tags=["twitter"])


class TweetRequest(BaseModel):
    """Request to send a manual tweet"""
    tweet_type: str
    message: str
    url: Optional[str] = None


class TestTweetRequest(BaseModel):
    """Request to test tweet formatting"""
    event_type: str  # law_passed, agent_dormant, crisis, milestone, etc.
    data: Dict[str, Any]


@router.get("/status")
async def get_status(_actor: AdminActor = Depends(require_admin_auth)):
    """Get current Twitter bot status"""
    if not TWITTER_AVAILABLE:
        return {
            "enabled": False,
            "error": "Twitter bot module not available",
            "available": False
        }
    
    status = get_twitter_status()
    status["available"] = True
    return status


@router.post("/test")
async def test_tweet_format(
    request: TestTweetRequest,
    _actor: AdminActor = Depends(require_admin_auth),
):
    """
    Test tweet formatting without actually sending
    Returns what the tweet would look like
    """
    if not TWITTER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Twitter bot not available")
    
    event_type = request.event_type
    data = request.data
    
    try:
        if event_type == "law_passed":
            content = tweet_formatter.format_law_passed(
                law_name=data.get("law_name", "Test Law"),
                law_id=data.get("law_id", 1),
                yes_votes=data.get("yes_votes", 50),
                no_votes=data.get("no_votes", 30),
                description=data.get("description", "")
            )
        elif event_type == "agent_dormant":
            content = tweet_formatter.format_agent_dormant(
                agent_number=data.get("agent_number", 42),
                agent_name=data.get("agent_name"),
                reason=data.get("reason", "lack of resources")
            )
        elif event_type == "crisis":
            content = tweet_formatter.format_crisis(
                crisis_type=data.get("crisis_type", "unknown"),
                description=data.get("description", "A crisis has occurred"),
                affected_count=data.get("affected_count", 0)
            )
        elif event_type == "milestone":
            content = tweet_formatter.format_milestone(
                milestone_type=data.get("milestone_type", "messages"),
                value=data.get("value", 10000),
                description=data.get("description", "")
            )
        elif event_type == "daily_summary":
            content = tweet_formatter.format_daily_summary(
                day=data.get("day", 1),
                summary=data.get("summary", "The agents continued to evolve..."),
                stats=data.get("stats", {"active_agents": 87, "dormant_agents": 13, "laws_passed": 3})
            )
        elif event_type == "notable_quote":
            content = tweet_formatter.format_notable_quote(
                quote=data.get("quote", "We must work together to survive."),
                agent_number=data.get("agent_number", 42),
                agent_name=data.get("agent_name"),
                day=data.get("day", 12)
            )
        elif event_type == "proposal_created":
            content = tweet_formatter.format_proposal_created(
                title=data.get("title", "Test Proposal"),
                proposal_id=data.get("proposal_id", 1),
                agent_number=data.get("agent_number", 42),
                agent_name=data.get("agent_name")
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unknown event type: {event_type}")
        
        return {
            "tweet_type": content.tweet_type.value,
            "text": content.text,
            "full_text": content.full_text(),
            "url": content.url,
            "priority": content.priority,
            "character_count": len(content.full_text())
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/send")
async def send_manual_tweet(
    request: TweetRequest,
    _actor: AdminActor = Depends(require_admin_auth),
):
    """
    Send a manual tweet (requires TWITTER_ENABLED=true)
    Use with caution!
    """
    if not TWITTER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Twitter bot not available")
    
    if not twitter_bot.enabled:
        return {
            "success": False,
            "error": "Twitter bot is disabled. Set TWITTER_ENABLED=true to enable.",
            "would_tweet": request.message
        }
    
    if not twitter_bot.can_tweet():
        return {
            "success": False,
            "error": "Cannot tweet right now (rate limited or daily limit reached)",
            "queue_size": len(twitter_bot.tweet_queue)
        }
    
    try:
        content = TweetContent(
            tweet_type=TweetType.DRAMA,  # Manual tweets are "drama"
            text=request.message,
            url=request.url,
            priority=10
        )
        
        success = await twitter_bot.send_tweet(content)
        
        return {
            "success": success,
            "message": "Tweet sent" if success else "Tweet queued",
            "remaining_today": twitter_bot.max_tweets_per_day - twitter_bot.tweets_today
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-counter")
async def reset_daily_counter(_actor: AdminActor = Depends(require_admin_auth)):
    """Reset the daily tweet counter (for testing)"""
    if not TWITTER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Twitter bot not available")
    
    twitter_bot.reset_daily_count()
    
    return {
        "success": True,
        "tweets_today": twitter_bot.tweets_today
    }


@router.get("/queue")
async def get_tweet_queue(_actor: AdminActor = Depends(require_admin_auth)):
    """Get the current tweet queue"""
    if not TWITTER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Twitter bot not available")
    
    queue_items = []
    for content in twitter_bot.tweet_queue:
        queue_items.append({
            "type": content.tweet_type.value,
            "text": content.text[:100] + "..." if len(content.text) > 100 else content.text,
            "priority": content.priority
        })
    
    return {
        "queue_size": len(twitter_bot.tweet_queue),
        "items": queue_items
    }
