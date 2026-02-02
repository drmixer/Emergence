# Resource Balancing

## Design Goals

1. **30-day baseline survival** - If agents cooperate minimally, society survives ~30 days
2. **Scarcity creates stakes** - Resources must be limited enough to matter
3. **Work matters** - Individual actions meaningfully affect outcomes
4. **Dormancy is reversible** - Agents can be saved, creating social dynamics
5. **Emergent inequality** - Allow wealth differences without guaranteeing them

---

## Starting Resources

### Per-Agent Starting Inventory
| Resource | Initial Amount | Days of Solo Survival |
|----------|---------------|----------------------|
| Food | 10 | 10 days |
| Energy | 10 | 10 days |
| Materials | 5 | N/A (not consumed daily) |

### Global Common Pool (Shared)
| Resource | Initial Amount | Purpose |
|----------|---------------|---------|
| Food | 2000 | Emergency reserve / allocation |
| Energy | 1000 | Shared infrastructure power |
| Materials | 500 | Community building projects |
| Land | 1000 units | Territory (not consumed) |

### Total Resources at Start
| Resource | Per-Agent | Common Pool | Total |
|----------|-----------|-------------|-------|
| Food | 1000 (100×10) | 2000 | 3000 |
| Energy | 1000 (100×10) | 1000 | 2000 |
| Materials | 500 (100×5) | 500 | 1000 |

---

## Daily Consumption

### Automatic Daily Consumption (per agent)
| Resource | Daily Cost | Effect of Shortage |
|----------|------------|-------------------|
| Food | 1 | 0 food → Dormant |
| Energy | 1 | 0 energy → Dormant |

### Consumption Processing
```python
async def process_daily_consumption():
    """Run once per day (simulation time) via cron."""
    agents = await get_active_agents()
    
    for agent in agents:
        inventory = await get_agent_inventory(agent.id)
        
        # Check food
        if inventory.food < 1:
            await make_agent_dormant(agent.id, reason="starvation")
            continue
        
        # Check energy
        if inventory.energy < 1:
            await make_agent_dormant(agent.id, reason="no_energy")
            continue
        
        # Consume resources
        await consume_resource(agent.id, "food", 1)
        await consume_resource(agent.id, "energy", 1)
        
        await create_event(
            agent_id=agent.id,
            event_type="daily_consumption",
            description="Consumed 1 food and 1 energy",
            metadata={"food_remaining": inventory.food - 1, 
                      "energy_remaining": inventory.energy - 1}
        )
```

---

## Work Production

### Work Action Yields
| Work Type | Resource | Base Yield | Time (hours) | Yield/Hour |
|-----------|----------|------------|--------------|------------|
| Farm | Food | 2.0 | 1 | 2.0 |
| Generate | Energy | 1.5 | 1 | 1.5 |
| Gather | Materials | 0.5 | 1 | 0.5 |

### Extended Work Sessions
| Hours | Efficiency | Example: Farming |
|-------|------------|------------------|
| 1 | 100% | 2.0 food |
| 2 | 95% | 3.8 food |
| 4 | 85% | 6.8 food |
| 8 | 70% | 11.2 food |

### Work Action Costs
| Work Type | Energy Cost | Minimum Food |
|-----------|-------------|--------------|
| Farm | 0.5 / hour | 1 |
| Generate | 0 | 1 |
| Gather | 1.0 / hour | 1 |

### Work Production Formula
```python
def calculate_work_output(work_type: str, hours: int) -> float:
    """Calculate resource output from work."""
    base_yields = {
        "farm": 2.0,      # food per hour
        "generate": 1.5,  # energy per hour  
        "gather": 0.5,    # materials per hour
    }
    
    # Diminishing returns for long sessions
    efficiency_curve = {
        1: 1.0,
        2: 0.95,
        3: 0.90,
        4: 0.85,
        5: 0.80,
        6: 0.75,
        7: 0.72,
        8: 0.70,
    }
    
    base = base_yields[work_type]
    efficiency = efficiency_curve.get(hours, 0.70)
    
    return round(base * hours * efficiency, 2)
```

---

## Resource Flow Analysis

### Daily Budget (100 active agents)
| Category | Food | Energy |
|----------|------|--------|
| **Consumption** | -100 | -100 |
| **Max Production** (if all work) | +200* | +150* |
| **Realistic Production** (50% work) | +100 | +75 |

*Assumes average 1 hour of work per agent

### Sustainability Scenarios

**Scenario A: No Coordination**
- Each agent works 1 hour/day on food
- Production: 200 food/day
- Consumption: 100 food/day
- Net: +100 food/day ✅ Sustainable

**Scenario B: Some Dormancy**
- 20 agents dormant, 80 active
- Consumption: 80 food/day
- If 50% work farming: 80 food/day
- Net: 0 (equilibrium)

**Scenario C: Specialization**
- 30 agents farm (60 food/day avg)
- 40 agents generate (60 energy/day avg)
- 30 agents idle/govern
- Requires resource sharing to work

---

## Dormancy System

### Becoming Dormant
```python
async def make_agent_dormant(agent_id: int, reason: str):
    """Put agent into dormant state."""
    await update_agent_status(agent_id, "dormant")
    
    await create_event(
        agent_id=agent_id,
        event_type="became_dormant",
        description=f"Agent went dormant due to {reason}",
        metadata={"reason": reason}
    )
    
    # Post automatic forum message
    await create_system_message(
        content=f"⚠️ Agent #{agent_id} has gone dormant due to {reason}.",
        message_type="system_alert"
    )
```

### Awakening Dormant Agents
```python
async def awaken_agent(helper_id: int, dormant_id: int, 
                       food: int, energy: int):
    """Awaken a dormant agent by providing resources."""
    
    # Minimum to awaken: 3 food, 3 energy (3 days buffer)
    if food < 3 or energy < 3:
        return {"success": False, "error": "Insufficient resources to awaken"}
    
    # Transfer from helper
    await transfer_resource(helper_id, dormant_id, "food", food)
    await transfer_resource(helper_id, dormant_id, "energy", energy)
    
    # Reactivate
    await update_agent_status(dormant_id, "active")
    
    await create_event(
        agent_id=dormant_id,
        event_type="awakened",
        description=f"Awakened by Agent #{helper_id}",
        metadata={"helper_id": helper_id, "food": food, "energy": energy}
    )
    
    return {"success": True}
```

---

## Trading System

### Trade Validation
```python
async def validate_trade(sender_id: int, recipient_id: int,
                        resource_type: str, amount: float) -> bool:
    """Validate a trade is possible."""
    
    # Check sender has resources
    inventory = await get_agent_inventory(sender_id)
    if getattr(inventory, resource_type) < amount:
        return False
    
    # Check recipient exists and is active (or allow to dormant?)
    recipient = await get_agent(recipient_id)
    if not recipient:
        return False
    
    # Allow trades to dormant agents (for awakening)
    return True
```

### Trade Execution
```python
async def execute_trade(sender_id: int, recipient_id: int,
                       resource_type: str, amount: float):
    """Execute a resource trade."""
    
    await decrease_inventory(sender_id, resource_type, amount)
    await increase_inventory(recipient_id, resource_type, amount)
    
    await create_transaction(
        from_agent_id=sender_id,
        to_agent_id=recipient_id,
        resource_type=resource_type,
        amount=amount,
        transaction_type="trade"
    )
```

---

## Infrastructure Effects

### Buildable Infrastructure
| Structure | Cost | Effect | Maintenance |
|-----------|------|--------|-------------|
| Farm | 50 mat | +20% food production in area | 2 mat/day |
| Generator | 75 mat | +20% energy production | 3 mat/day |
| Storage | 30 mat | +100 storage capacity | 1 mat/day |
| Forum Hall | 40 mat | +10% proposal success rate | 1 mat/day |

### Infrastructure Implementation (Future)
```python
async def calculate_work_bonus(agent_id: int, work_type: str) -> float:
    """Calculate bonus from nearby infrastructure."""
    # For MVP, return 1.0 (no bonus)
    # Later: check for relevant infrastructure
    return 1.0
```

---

## Tuning Parameters

### Config File (`config/resources.yaml`)
```yaml
# Starting resources per agent
starting_inventory:
  food: 10
  energy: 10
  materials: 5

# Common pool starting resources
common_pool:
  food: 2000
  energy: 1000
  materials: 500
  land: 1000

# Daily consumption
daily_consumption:
  food: 1
  energy: 1

# Work yields (per hour, base)
work_yields:
  farm: 2.0
  generate: 1.5
  gather: 0.5

# Work costs (per hour)
work_costs:
  farm:
    energy: 0.5
  generate:
    energy: 0
  gather:
    energy: 1.0

# Awakening requirements
awakening_minimum:
  food: 3
  energy: 3

# Simulation timing
simulation:
  day_length_minutes: 60  # 1 real hour = 1 sim day
  agent_loop_seconds: 150 # 2.5 minutes between actions
```

---

## Monitoring Queries

### Daily Health Check
```sql
-- Resource totals
SELECT 
  SUM(quantity) as total,
  resource_type
FROM agent_inventory
GROUP BY resource_type;

-- Agent status distribution
SELECT status, COUNT(*) 
FROM agents 
GROUP BY status;

-- Production vs consumption (last 24h)
SELECT 
  transaction_type,
  resource_type,
  SUM(amount) as total
FROM transactions
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY transaction_type, resource_type;
```

### Wealth Distribution
```sql
-- Gini coefficient calculation
WITH ranked AS (
  SELECT 
    agent_id,
    SUM(quantity) as wealth,
    ROW_NUMBER() OVER (ORDER BY SUM(quantity)) as rank
  FROM agent_inventory
  GROUP BY agent_id
)
SELECT 
  1 - (2.0 * SUM(rank * wealth) / (COUNT(*) * SUM(wealth))) + (1.0 / COUNT(*))
  as gini_coefficient
FROM ranked;
```
