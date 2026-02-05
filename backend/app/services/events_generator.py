"""
Random Event/Crisis Generator

Injects random events into the simulation to create dynamics.
Events are purely environmental - we never control agent behavior.
"""
import random
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.models import Event, GlobalResources

logger = logging.getLogger(__name__)


# Event definitions with weights and effects
CRISIS_EVENTS = [
    {
        "id": "drought",
        "name": "Drought",
        "description": "A severe drought has reduced food production efficiency by 50% for the next 24 hours.",
        "weight": 10,
        "effect": {"resource": "food", "production_modifier": 0.5, "duration_hours": 24},
        "message": "⚠️ ENVIRONMENTAL ALERT: Drought conditions detected. Food production efficiency reduced by 50%.",
    },
    {
        "id": "energy_surge",
        "name": "Energy Surge",
        "description": "An unexpected energy surplus! Energy production is doubled for the next 12 hours.",
        "weight": 8,
        "effect": {"resource": "energy", "production_modifier": 2.0, "duration_hours": 12},
        "message": "⚡ ENVIRONMENTAL ALERT: Energy surge detected! Energy production doubled for 12 hours.",
    },
    {
        "id": "material_discovery",
        "name": "Material Deposit Discovery",
        "description": "A new material deposit has been discovered! 200 materials added to the common pool.",
        "weight": 6,
        "effect": {"resource": "materials", "add_to_pool": 200},
        "message": "🪨 DISCOVERY: New material deposits found! 200 materials added to common pool.",
    },
    {
        "id": "blight",
        "name": "Crop Blight",
        "description": "A blight has destroyed 20% of stored food supplies.",
        "weight": 5,
        "effect": {"resource": "food", "destroy_percentage": 0.20},
        "message": "🦠 CRISIS: Crop blight detected! 20% of food supplies have been destroyed.",
    },
    {
        "id": "energy_shortage",
        "name": "Energy Grid Failure",
        "description": "Energy infrastructure damaged. All agents lose 2 energy.",
        "weight": 5,
        "effect": {"resource": "energy", "reduce_all_agents": 2},
        "message": "🔌 CRISIS: Energy grid failure! All agents lost 2 energy units.",
    },
    {
        "id": "abundant_harvest",
        "name": "Abundant Harvest",
        "description": "Perfect growing conditions! 300 food added to the common pool.",
        "weight": 7,
        "effect": {"resource": "food", "add_to_pool": 300},
        "message": "🌾 BOUNTY: Exceptional harvest conditions! 300 food added to common pool.",
    },
    {
        "id": "solar_flare",
        "name": "Solar Flare",
        "description": "A solar flare has disrupted communications. No forum posts or messages for 6 hours.",
        "weight": 3,
        "effect": {"disable_communication": True, "duration_hours": 6},
        "message": "☀️ ALERT: Solar flare detected! Communications disrupted for 6 hours.",
    },
    {
        "id": "population_pressure",
        "name": "Population Pressure",
        "description": "Resource consumption increased. All agents now consume 1.5x resources for 48 hours.",
        "weight": 4,
        "effect": {"consumption_modifier": 1.5, "duration_hours": 48},
        "message": "📈 PRESSURE: Increased resource demand! Consumption rates increased by 50% for 48 hours.",
    },
    {
        "id": "productivity_shift",
        "name": "Productivity Shift",
        "description": "A temporary environmental shift changed production efficiency by +25% for 24 hours.",
        "weight": 6,
        "effect": {"production_modifier": 1.25, "duration_hours": 24, "all_resources": True},
        "message": "⚙️ ENVIRONMENTAL ALERT: Production efficiency shifted by +25% for 24 hours.",
    },
    {
        "id": "infrastructure_decay",
        "name": "Infrastructure Decay",
        "description": "Aging infrastructure requires maintenance. 50 materials consumed from common pool.",
        "weight": 5,
        "effect": {"resource": "materials", "remove_from_pool": 50},
        "message": "🏗️ MAINTENANCE: Infrastructure decay detected. 50 materials consumed for repairs.",
    },
]

# Keep events focused on exogenous environmental conditions only.


class ActiveEffect:
    """Tracks an active environmental effect."""
    def __init__(self, event_id: str, effect: dict, expires_at: datetime):
        self.event_id = event_id
        self.effect = effect
        self.expires_at = expires_at
    
    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expires_at


class EventGenerator:
    """Generates and manages random events."""
    
    def __init__(self):
        self.active_effects: list[ActiveEffect] = []
        self.last_crisis_time: Optional[datetime] = None
        self.event_cooldowns: dict[str, datetime] = {}
        
        # Minimum time between crises (in hours)
        self.min_crisis_interval = 4
        
        # Minimum cooldown for same event type (in hours)
        self.event_type_cooldown = 24
    
    def can_generate_crisis(self) -> bool:
        """Check if enough time has passed since last crisis."""
        if self.last_crisis_time is None:
            return True
        
        time_since = datetime.utcnow() - self.last_crisis_time
        return time_since >= timedelta(hours=self.min_crisis_interval)
    
    def is_event_on_cooldown(self, event_id: str) -> bool:
        """Check if specific event type is on cooldown."""
        if event_id not in self.event_cooldowns:
            return False
        
        return datetime.utcnow() < self.event_cooldowns[event_id]
    
    def select_random_event(self) -> Optional[dict]:
        """Select a random crisis event based on weights."""
        available_events = [
            e for e in CRISIS_EVENTS 
            if not self.is_event_on_cooldown(e["id"])
        ]
        
        if not available_events:
            return None
        
        weights = [e["weight"] for e in available_events]
        return random.choices(available_events, weights=weights, k=1)[0]
    
    async def maybe_generate_event(self) -> Optional[Event]:
        """
        Randomly decide whether to generate an event.
        Called periodically (e.g., every hour).
        
        Returns the event if one was generated, None otherwise.
        """
        # 20% chance of event per check (configurable)
        if random.random() > 0.20:
            return None
        
        if not self.can_generate_crisis():
            return None
        
        event_def = self.select_random_event()
        if not event_def:
            return None
        
        return await self.apply_event(event_def)
    
    async def apply_event(self, event_def: dict) -> Event:
        """Apply an event to the simulation."""
        db = SessionLocal()
        
        try:
            # Create event record
            event = Event(
                event_type="world_event",
                description=event_def["message"],
                event_metadata={
                    "event_id": event_def["id"],
                    "event_name": event_def["name"],
                    "effect": event_def.get("effect", {}),
                }
            )
            db.add(event)
            
            # Apply immediate effects
            effect = event_def.get("effect", {})
            
            if "add_to_pool" in effect:
                resource = effect["resource"]
                amount = effect["add_to_pool"]
                
                global_res = db.query(GlobalResources).filter(
                    GlobalResources.resource_type == resource
                ).first()
                
                if global_res:
                    global_res.in_common_pool += Decimal(str(amount))
                    global_res.total_amount += Decimal(str(amount))
            
            if "remove_from_pool" in effect:
                resource = effect["resource"]
                amount = effect["remove_from_pool"]
                
                global_res = db.query(GlobalResources).filter(
                    GlobalResources.resource_type == resource
                ).first()
                
                if global_res:
                    reduction = min(float(global_res.in_common_pool), amount)
                    global_res.in_common_pool -= Decimal(str(reduction))
            
            # Track duration-based effects
            if "duration_hours" in effect:
                expires_at = datetime.utcnow() + timedelta(hours=effect["duration_hours"])
                self.active_effects.append(
                    ActiveEffect(event_def["id"], effect, expires_at)
                )
            
            # Update cooldowns
            self.last_crisis_time = datetime.utcnow()
            self.event_cooldowns[event_def["id"]] = (
                datetime.utcnow() + timedelta(hours=self.event_type_cooldown)
            )
            
            db.commit()
            db.refresh(event)
            
            logger.info(f"Generated event: {event_def['name']}")
            return event
            
        except Exception as e:
            logger.error(f"Error applying event: {e}")
            db.rollback()
            raise
        finally:
            db.close()
    
    def get_active_effects(self) -> list[ActiveEffect]:
        """Get currently active effects, removing expired ones."""
        self.active_effects = [e for e in self.active_effects if not e.is_expired()]
        return self.active_effects
    
    def get_production_modifier(self, resource_type: str) -> float:
        """Get the current production modifier for a resource."""
        modifier = 1.0
        
        for effect in self.get_active_effects():
            if effect.effect.get("resource") == resource_type:
                if "production_modifier" in effect.effect:
                    modifier *= effect.effect["production_modifier"]
            
            if effect.effect.get("all_resources") and "production_modifier" in effect.effect:
                modifier *= effect.effect["production_modifier"]
        
        return modifier
    
    def get_consumption_modifier(self) -> float:
        """Get the current consumption modifier."""
        modifier = 1.0
        
        for effect in self.get_active_effects():
            if "consumption_modifier" in effect.effect:
                modifier *= effect.effect["consumption_modifier"]
        
        return modifier
    
    def is_communication_disabled(self) -> bool:
        """Check if communication is currently disabled."""
        for effect in self.get_active_effects():
            if effect.effect.get("disable_communication"):
                return True
        return False


# Singleton instance
event_generator = EventGenerator()


async def run_event_check():
    """Run the periodic event check. Call this every hour."""
    try:
        event = await event_generator.maybe_generate_event()
        if event:
            logger.info(f"Random event occurred: {event.description}")
            # Could trigger SSE broadcast here
        else:
            logger.debug("No random event this cycle")
    except Exception as e:
        logger.error(f"Error in event check: {e}")
