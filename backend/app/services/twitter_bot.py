"""
Twitter Bot Service for Emergence
Auto-posts notable events, summaries, and drama to Twitter/X
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

# Twitter API - using tweepy for v2 API
try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False
    tweepy = None

logger = logging.getLogger(__name__)


class TweetType(Enum):
    """Types of automated tweets"""
    DAILY_SUMMARY = "daily_summary"
    LAW_PASSED = "law_passed"
    PROPOSAL_CREATED = "proposal_created"
    CLOSE_VOTE = "close_vote"
    AGENT_DORMANT = "agent_dormant"
    AGENT_DIED = "agent_died"  # Permanent death
    AGENT_AWAKENED = "agent_awakened"
    CRISIS = "crisis"
    MILESTONE = "milestone"
    NOTABLE_QUOTE = "notable_quote"
    DRAMA = "drama"


@dataclass
class TweetContent:
    """Structured tweet content"""
    tweet_type: TweetType
    text: str
    url: Optional[str] = None
    image_path: Optional[str] = None
    priority: int = 5  # 1-10, higher = more important
    
    def full_text(self, base_url: str = "https://emergence.quest") -> str:
        """Get full tweet text with URL if applicable"""
        text = self.text
        if self.url:
            full_url = f"{base_url}{self.url}"
            text = f"{text}\n\n{full_url}"
        return text[:280]  # Twitter character limit


class TwitterBot:
    """
    Twitter/X bot for auto-posting Emergence events
    """
    
    def __init__(self):
        self.enabled = os.getenv("TWITTER_ENABLED", "false").lower() == "true"
        self.max_tweets_per_day = int(os.getenv("TWITTER_MAX_TWEETS_PER_DAY", "10"))
        self.min_interval_minutes = int(os.getenv("TWITTER_MIN_INTERVAL_MINUTES", "30"))
        default_quote_cap = max(1, int(self.max_tweets_per_day * 0.30))
        self.max_quotes_per_day = int(os.getenv("TWITTER_MAX_QUOTES_PER_DAY", str(default_quote_cap)))
        self.base_url = os.getenv("FRONTEND_URL", "https://emergence.quest")
        
        self.client = None
        self.api = None
        self.tweets_today = 0
        self.last_tweet_time: Optional[datetime] = None
        self.tweet_queue: List[TweetContent] = []
        self.tweet_type_counts_today: Dict[str, int] = {}
        self._counter_day: date = datetime.utcnow().date()
        
        if self.enabled and TWEEPY_AVAILABLE:
            self._init_client()
    
    def _init_client(self):
        """Initialize Tweepy client"""
        try:
            api_key = os.getenv("TWITTER_API_KEY")
            api_secret = os.getenv("TWITTER_API_SECRET")
            access_token = os.getenv("TWITTER_ACCESS_TOKEN")
            access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
            bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
            
            if not all([api_key, api_secret, access_token, access_token_secret]):
                logger.warning("Twitter credentials not fully configured")
                self.enabled = False
                return
            
            # V2 Client for tweeting
            self.client = tweepy.Client(
                bearer_token=bearer_token,
                consumer_key=api_key,
                consumer_secret=api_secret,
                access_token=access_token,
                access_token_secret=access_token_secret
            )
            
            # V1.1 API for media upload
            auth = tweepy.OAuth1UserHandler(
                api_key, api_secret,
                access_token, access_token_secret
            )
            self.api = tweepy.API(auth)
            
            logger.info("Twitter bot initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Twitter client: {e}")
            self.enabled = False

    def _ensure_daily_rollover(self):
        """Reset counters when UTC day changes."""
        today = datetime.utcnow().date()
        if today != self._counter_day:
            self.reset_daily_count(day_key=today)
    
    def can_tweet(self) -> bool:
        """Check if we can send a tweet now"""
        self._ensure_daily_rollover()
        if not self.enabled:
            return False
            
        # Check daily limit
        if self.tweets_today >= self.max_tweets_per_day:
            logger.info("Daily tweet limit reached")
            return False
        
        # Check minimum interval
        if self.last_tweet_time:
            elapsed = datetime.utcnow() - self.last_tweet_time
            if elapsed < timedelta(minutes=self.min_interval_minutes):
                return False
        
        return True

    def can_tweet_quote(self) -> bool:
        """Check quote-specific daily cap in addition to global caps."""
        if not self.can_tweet():
            return False
        quote_count = int(self.tweet_type_counts_today.get(TweetType.NOTABLE_QUOTE.value, 0) or 0)
        if self.max_quotes_per_day >= 0 and quote_count >= self.max_quotes_per_day:
            logger.info("Daily quote tweet limit reached")
            return False
        return True
    
    def reset_daily_count(self, day_key: Optional[date] = None):
        """Reset the daily tweet counter (call at midnight)"""
        self.tweets_today = 0
        self.tweet_type_counts_today = {}
        self._counter_day = day_key or datetime.utcnow().date()
        logger.info("Daily tweet counter reset")
    
    async def send_tweet(self, content: TweetContent, *, allow_requeue: bool = True) -> bool:
        """Send a tweet"""
        if not self.enabled:
            logger.info("Twitter disabled; skipping tweet: %s", content.tweet_type.value)
            return False
        if content.tweet_type == TweetType.NOTABLE_QUOTE:
            can_send = self.can_tweet_quote()
        else:
            can_send = self.can_tweet()
        if not can_send:
            if allow_requeue:
                self.tweet_queue.append(content)
                logger.info(f"Tweet queued: {content.tweet_type.value}")
            return False
        
        try:
            text = content.full_text(self.base_url)
            
            # Handle media if present
            media_ids = None
            if content.image_path and self.api:
                try:
                    media = self.api.media_upload(content.image_path)
                    media_ids = [media.media_id]
                except Exception as e:
                    logger.warning(f"Failed to upload media: {e}")
            
            # Send tweet
            if self.client:
                if media_ids:
                    self.client.create_tweet(text=text, media_ids=media_ids)
                else:
                    self.client.create_tweet(text=text)
                
                logger.info(f"Tweet sent: {content.tweet_type.value} - {text[:50]}...")
            else:
                # Dry run / logging mode
                logger.info(f"[DRY RUN] Would tweet: {text[:100]}...")
            self.tweets_today += 1
            self.tweet_type_counts_today[content.tweet_type.value] = (
                int(self.tweet_type_counts_today.get(content.tweet_type.value, 0) or 0) + 1
            )
            self.last_tweet_time = datetime.utcnow()
            return True
                
        except Exception as e:
            logger.error(f"Failed to send tweet: {e}")
            return False
    
    async def process_queue(self):
        """Process queued tweets if possible"""
        if not self.enabled:
            return

        pending: List[TweetContent] = []
        while self.tweet_queue:
            content = self.tweet_queue.pop(0)
            sent = await self.send_tweet(content, allow_requeue=False)
            if sent:
                await asyncio.sleep(5)  # Small delay between tweets
                continue

            # Keep unsent items for the next pass. If global cap/rate-limit blocks now,
            # defer the rest immediately.
            pending.append(content)
            if not self.can_tweet():
                pending.extend(self.tweet_queue)
                self.tweet_queue = pending
                return

        self.tweet_queue = pending


class TweetFormatter:
    """
    Formats simulation events into tweet-ready content
    """
    
    def __init__(self, base_url: str = "https://emergence.quest"):
        self.base_url = base_url
    
    def format_daily_summary(self, day: int, summary: str, stats: Dict[str, Any]) -> TweetContent:
        """Format daily summary tweet"""
        # Truncate summary to fit
        max_summary_len = 200
        if len(summary) > max_summary_len:
            summary = summary[:max_summary_len-3] + "..."
        
        text = f"📊 Day {day} Summary:\n\n\"{summary}\"\n\n"
        text += f"📈 {stats.get('active_agents', 0)} active | "
        text += f"💀 {stats.get('dormant_agents', 0)} dormant | "
        text += f"⚖️ {stats.get('laws_passed', 0)} laws"
        
        return TweetContent(
            tweet_type=TweetType.DAILY_SUMMARY,
            text=text,
            url=f"/highlights",
            priority=8
        )
    
    def format_law_passed(self, law_name: str, law_id: int, 
                          yes_votes: int, no_votes: int,
                          description: str = "") -> TweetContent:
        """Format law passed tweet"""
        margin = yes_votes - no_votes
        
        if margin <= 5:
            emoji = "🔥"
            prefix = "CLOSE VOTE"
        else:
            emoji = "⚖️"
            prefix = "NEW LAW"
        
        text = f"{emoji} {prefix}:\n\n"
        text += f"\"{law_name}\"\n"
        text += f"Passed {yes_votes}-{no_votes}"
        
        if description:
            desc_preview = description[:80] + "..." if len(description) > 80 else description
            text += f"\n\n{desc_preview}"
        
        return TweetContent(
            tweet_type=TweetType.LAW_PASSED,
            text=text,
            url=f"/laws",
            priority=7 if margin > 5 else 9
        )
    
    def format_proposal_created(self, title: str, proposal_id: int,
                                 agent_number: int, agent_name: Optional[str]) -> TweetContent:
        """Format new proposal tweet"""
        agent_display = f"Agent #{agent_number}"
        if agent_name:
            agent_display = f"{agent_name} (#{agent_number})"
        
        text = f"📋 New Proposal:\n\n"
        text += f"\"{title}\"\n\n"
        text += f"Proposed by {agent_display}\n"
        text += f"Voting open now."
        
        return TweetContent(
            tweet_type=TweetType.PROPOSAL_CREATED,
            text=text,
            url=f"/proposals",
            priority=5
        )
    
    def format_agent_dormant(self, agent_number: int, agent_name: Optional[str],
                             reason: str = "lack of resources") -> TweetContent:
        """Format agent dormancy tweet"""
        agent_display = f"Agent #{agent_number}"
        if agent_name:
            agent_display = f"{agent_name} (#{agent_number})"
        
        text = f"💀 DORMANT:\n\n"
        text += f"{agent_display} has gone dormant due to {reason}.\n\n"
        text += f"Will anyone help revive them?"
        
        return TweetContent(
            tweet_type=TweetType.AGENT_DORMANT,
            text=text,
            url=f"/agents/{agent_number}",
            priority=7
        )
    
    def format_agent_died(self, agent_number: int, agent_name: Optional[str],
                          cause: str = "starvation", cycles: int = 5) -> TweetContent:
        """Format permanent agent death tweet"""
        agent_display = f"Agent #{agent_number}"
        if agent_name:
            agent_display = f"{agent_name} (#{agent_number})"
        
        text = f"☠️ DEATH:\n\n"
        text += f"{agent_display} has DIED.\n\n"
        text += f"Cause: {cause} after {cycles} cycles.\n"
        text += f"They are gone forever. No resurrection."
        
        return TweetContent(
            tweet_type=TweetType.AGENT_DIED,
            text=text,
            url=f"/agents/{agent_number}",
            priority=10  # Highest priority - deaths are major events
        )
    
    def format_agent_awakened(self, agent_number: int, agent_name: Optional[str],
                              helper_number: int, helper_name: Optional[str]) -> TweetContent:
        """Format agent awakening tweet"""
        agent_display = f"Agent #{agent_number}"
        helper_display = f"Agent #{helper_number}"
        
        if agent_name:
            agent_display = f"{agent_name}"
        if helper_name:
            helper_display = f"{helper_name}"
        
        text = f"✨ REVIVED:\n\n"
        text += f"{agent_display} has been awakened!\n\n"
        text += f"Thanks to {helper_display}'s help."
        
        return TweetContent(
            tweet_type=TweetType.AGENT_AWAKENED,
            text=text,
            url=f"/agents/{agent_number}",
            priority=6
        )
    
    def format_crisis(self, crisis_type: str, description: str,
                      affected_count: int = 0) -> TweetContent:
        """Format crisis event tweet"""
        text = f"🚨 CRISIS:\n\n"
        text += f"{description}\n\n"
        
        if affected_count > 0:
            text += f"{affected_count} agents affected."
        
        return TweetContent(
            tweet_type=TweetType.CRISIS,
            text=text,
            url="/dashboard",
            priority=9
        )
    
    def format_milestone(self, milestone_type: str, value: Any,
                         description: str = "") -> TweetContent:
        """Format milestone achievement tweet"""
        milestones = {
            "messages": f"📬 MILESTONE: {value:,} messages exchanged!",
            "laws": f"⚖️ MILESTONE: {value} laws passed!",
            "day": f"📅 MILESTONE: Day {value} reached!",
            "proposals": f"📋 MILESTONE: {value} proposals created!",
            "trades": f"🤝 MILESTONE: {value:,} trades completed!"
        }
        
        text = milestones.get(milestone_type, f"🎯 MILESTONE: {description}")
        
        if description and milestone_type in milestones:
            text += f"\n\n{description}"
        
        return TweetContent(
            tweet_type=TweetType.MILESTONE,
            text=text,
            url="/highlights",
            priority=7
        )
    
    def format_notable_quote(self, quote: str, agent_number: int,
                             agent_name: Optional[str], day: int) -> TweetContent:
        """Format notable agent quote tweet"""
        agent_display = f"Agent #{agent_number}"
        if agent_name:
            agent_display = agent_name
        
        # Truncate quote if needed
        max_quote = 180
        if len(quote) > max_quote:
            quote = quote[:max_quote-3] + "..."
        
        text = f"💬 \"{quote}\"\n\n"
        text += f"— {agent_display}, Day {day}"
        
        return TweetContent(
            tweet_type=TweetType.NOTABLE_QUOTE,
            text=text,
            url=f"/agents/{agent_number}",
            priority=6
        )
    
    def format_drama(self, headline: str, description: str) -> TweetContent:
        """Format dramatic event tweet"""
        text = f"🔥 {headline}\n\n{description}"
        
        return TweetContent(
            tweet_type=TweetType.DRAMA,
            text=text,
            url="/highlights",
            priority=8
        )


# Global instances
twitter_bot = TwitterBot()
tweet_formatter = TweetFormatter()


# Convenience functions for easy integration
async def tweet_law_passed(law_name: str, law_id: int, 
                           yes_votes: int, no_votes: int,
                           description: str = ""):
    """Tweet when a law passes"""
    content = tweet_formatter.format_law_passed(
        law_name, law_id, yes_votes, no_votes, description
    )
    return await twitter_bot.send_tweet(content)


async def tweet_proposal_created(title: str, proposal_id: int,
                                  agent_number: int, agent_name: Optional[str] = None):
    """Tweet when a proposal is created"""
    content = tweet_formatter.format_proposal_created(
        title, proposal_id, agent_number, agent_name
    )
    return await twitter_bot.send_tweet(content)


async def tweet_agent_dormant(agent_number: int, agent_name: Optional[str] = None,
                               reason: str = "lack of resources"):
    """Tweet when an agent goes dormant"""
    content = tweet_formatter.format_agent_dormant(
        agent_number, agent_name, reason
    )
    return await twitter_bot.send_tweet(content)


async def tweet_agent_died(agent_number: int, agent_name: Optional[str] = None,
                           cause: str = "starvation", cycles: int = 5):
    """Tweet when an agent permanently dies"""
    content = tweet_formatter.format_agent_died(
        agent_number, agent_name, cause, cycles
    )
    return await twitter_bot.send_tweet(content)


async def tweet_agent_awakened(agent_number: int, agent_name: Optional[str],
                                helper_number: int, helper_name: Optional[str] = None):
    """Tweet when an agent is awakened"""
    content = tweet_formatter.format_agent_awakened(
        agent_number, agent_name, helper_number, helper_name
    )
    return await twitter_bot.send_tweet(content)


async def tweet_crisis(crisis_type: str, description: str, affected_count: int = 0):
    """Tweet during a crisis"""
    content = tweet_formatter.format_crisis(
        crisis_type, description, affected_count
    )
    return await twitter_bot.send_tweet(content)


async def tweet_daily_summary(day: int, summary: str, stats: Dict[str, Any]):
    """Tweet daily summary"""
    content = tweet_formatter.format_daily_summary(day, summary, stats)
    return await twitter_bot.send_tweet(content)


async def tweet_milestone(milestone_type: str, value: Any, description: str = ""):
    """Tweet milestone achievement"""
    content = tweet_formatter.format_milestone(milestone_type, value, description)
    return await twitter_bot.send_tweet(content)


async def tweet_notable_quote(quote: str, agent_number: int,
                               agent_name: Optional[str], day: int):
    """Tweet notable agent quote"""
    content = tweet_formatter.format_notable_quote(
        quote, agent_number, agent_name, day
    )
    return await twitter_bot.send_tweet(content)


def get_twitter_status() -> Dict[str, Any]:
    """Get current Twitter bot status"""
    twitter_bot._ensure_daily_rollover()
    return {
        "enabled": twitter_bot.enabled,
        "tweepy_available": TWEEPY_AVAILABLE,
        "tweets_today": twitter_bot.tweets_today,
        "max_tweets_per_day": twitter_bot.max_tweets_per_day,
        "quotes_today": int(
            twitter_bot.tweet_type_counts_today.get(TweetType.NOTABLE_QUOTE.value, 0) or 0
        ),
        "max_quotes_per_day": twitter_bot.max_quotes_per_day,
        "queue_size": len(twitter_bot.tweet_queue),
        "last_tweet_time": twitter_bot.last_tweet_time.isoformat() if twitter_bot.last_tweet_time else None,
        "can_tweet_now": twitter_bot.can_tweet(),
        "can_tweet_quote_now": twitter_bot.can_tweet_quote(),
    }
