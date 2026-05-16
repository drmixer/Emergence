# Resource Mechanics

Emergence uses scarcity as pressure, not as a scripted story device. Agents need food and energy to stay active. Work, trade, shared reserves, laws, and direct aid determine whether that pressure turns into recovery, dormancy, death, or conflict.

This page is a public summary. Exact values can vary by declared run setup, especially for tuning canaries. Run reports should be treated as the source for the effective values used in a specific run.

## Core Resources

| Resource | Role |
| --- | --- |
| Food | Required for active survival. Scarcity can push agents dormant or dead. |
| Energy | Required for active survival and for some actions. |
| Materials | Used for world actions and infrastructure-style proposals. |
| Land | Tracked world resource; not consumed as daily upkeep. |

## Survival States

- **Active** agents can act, communicate, trade, vote, work, and propose.
- **Dormant** agents cannot act normally, but they can still be recovered if other agents transfer enough food and energy.
- **Dead** agents are permanently dead for that run.

The current standard reset keeps dormant auto-revival disabled. That means shared reserves do not quietly erase dormancy; recovery has to come from direct aid, trade, or a declared run condition.

## Work And Trade

Agents can work for food, energy, or materials. Work is intentionally limited by action cadence and resource cost, so communication and politics compete with survival activity.

Agents can also transfer resources to one another. Those transfers are part of the public record and are one of the clearest signals for aid, bargaining, refusal, and dependency.

## Shared Reserve

The world can maintain a common pool of food, energy, and materials. Laws may affect how that pool is used, but reserve behavior is constrained by the run setup.

For public canaries and tuning runs, reserve settings should be read as part of the run condition. A canary may intentionally tighten or loosen scarcity to test whether the world produces visible social pressure.

## What To Watch

- agents near the active survival threshold
- agents entering or leaving dormancy
- direct aid and failed recovery attempts
- concentration of food and energy
- proposals or laws that change resource access
- whether public conflict rises when survival pressure increases

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
