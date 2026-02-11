"""Epoch tournament candidate scoring and deterministic champion selection."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
from typing import Any

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.orm import Session

from app.core.time import now_utc
from app.models.models import SimulationRun
from app.services.emergence_metrics import COOPERATION_EVENT_TYPES, CONFLICT_EVENT_TYPES

SCORING_POLICY_VERSION_V1 = "epoch_tournament_v1"
DEFAULT_CHAMPIONS_PER_SEASON = 2
DEFAULT_TARGET_CHAMPIONS = 8

MEANINGFUL_EVENT_TYPES = (
    "forum_post",
    "forum_reply",
    "direct_message",
    "create_proposal",
    "vote",
    "work",
    "trade",
    "vote_enforcement",
    "initiate_sanction",
    "initiate_seizure",
    "initiate_exile",
)

SANCTION_EVENT_TYPES = (
    "agent_sanctioned",
    "resources_seized",
    "agent_exiled",
)


def _coerce_identifier(raw_value: str | None, *, field_name: str) -> str:
    clean = str(raw_value or "").strip()
    if not clean:
        raise ValueError(f"{field_name} is required")
    if len(clean) > 64:
        raise ValueError(f"{field_name} must be <= 64 chars")
    if not re.match(r"^[A-Za-z0-9:_-]+$", clean):
        raise ValueError(f"{field_name} must match [A-Za-z0-9:_-]+")
    return clean


def _reports_root() -> Path:
    return Path(__file__).resolve().parents[3] / "output" / "reports"


def _slug_fragment(raw_value: str, *, fallback: str = "epoch") -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(raw_value or "").strip().lower()).strip("-")
    return normalized or fallback


def _artifact_dir_for_epoch(epoch_id: str) -> Path:
    directory = _reports_root() / "epochs" / _slug_fragment(epoch_id, fallback="epoch")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _coerce_season_ids(season_ids: list[str] | tuple[str, ...] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in season_ids or []:
        clean = _coerce_identifier(raw_value, field_name="season_id")
        if clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)
    return normalized


def _has_table(db: Session, table_name: str) -> bool:
    try:
        return bool(inspect(db.bind).has_table(table_name))
    except Exception:
        return False


def _build_candidate_query(*, include_lineage: bool, include_season_filter: bool):
    lineage_cte = (
        """
lineage_flags AS (
    SELECT
      al.season_id,
      al.child_agent_number,
      CASE WHEN SUM(CASE WHEN al.origin = 'carryover' THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END AS is_carryover_agent
    FROM agent_lineage al
    GROUP BY al.season_id, al.child_agent_number
),
"""
        if include_lineage
        else
        """
lineage_flags AS (
    SELECT
      CAST(NULL AS TEXT) AS season_id,
      CAST(NULL AS INTEGER) AS child_agent_number,
      CAST(0 AS INTEGER) AS is_carryover_agent
    WHERE 1 = 0
),
"""
    )

    season_filter = "AND r.season_id IN :season_ids" if include_season_filter else ""

    query = text(
        f"""
WITH run_pool AS (
    SELECT DISTINCT
      r.run_id,
      r.season_id,
      COALESCE(r.carryover_agent_count, 0) AS carryover_agent_count
    FROM simulation_runs r
    WHERE r.epoch_id = :epoch_id
      AND r.season_id IS NOT NULL
      AND TRIM(r.season_id) <> ''
      AND r.ended_at IS NOT NULL
      AND COALESCE(r.run_class, 'standard_72h') <> 'special_exploratory'
      {season_filter}
),
season_flags AS (
    SELECT
      rp.season_id,
      CASE WHEN MAX(CASE WHEN rp.carryover_agent_count > 0 THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END AS is_carryover_season
    FROM run_pool rp
    GROUP BY rp.season_id
),
events_scoped AS (
    SELECT
      rp.season_id,
      rp.run_id,
      e.agent_id,
      e.event_type
    FROM events e
    JOIN run_pool rp ON (e.event_metadata -> 'runtime' ->> 'run_id') = rp.run_id
    WHERE e.agent_id IS NOT NULL
),
llm_scoped AS (
    SELECT
      rp.season_id,
      rp.run_id,
      u.agent_id,
      u.success
    FROM llm_usage u
    JOIN run_pool rp ON u.run_id = rp.run_id
    WHERE u.agent_id IS NOT NULL
),
run_agent_presence AS (
    SELECT season_id, run_id, agent_id FROM events_scoped
    UNION
    SELECT season_id, run_id, agent_id FROM llm_scoped
),
run_agent_death AS (
    SELECT
      season_id,
      run_id,
      agent_id,
      SUM(CASE WHEN event_type = 'agent_died' THEN 1 ELSE 0 END) AS death_events_in_run
    FROM events_scoped
    GROUP BY season_id, run_id, agent_id
),
active_end_by_agent AS (
    SELECT
      p.season_id,
      p.agent_id,
      MAX(CASE WHEN COALESCE(d.death_events_in_run, 0) = 0 THEN 1 ELSE 0 END) AS active_at_end_any_run
    FROM run_agent_presence p
    LEFT JOIN run_agent_death d
      ON d.season_id = p.season_id
     AND d.run_id = p.run_id
     AND d.agent_id = p.agent_id
    GROUP BY p.season_id, p.agent_id
),
meaningful_counts AS (
    SELECT
      season_id,
      agent_id,
      COUNT(*) AS meaningful_actions
    FROM events_scoped
    WHERE event_type IN :meaningful_event_types
    GROUP BY season_id, agent_id
),
invalid_counts AS (
    SELECT
      season_id,
      agent_id,
      COUNT(*) AS invalid_actions
    FROM events_scoped
    WHERE event_type = 'invalid_action'
    GROUP BY season_id, agent_id
),
dormant_counts AS (
    SELECT
      season_id,
      agent_id,
      COUNT(*) AS became_dormant_count
    FROM events_scoped
    WHERE event_type = 'became_dormant'
    GROUP BY season_id, agent_id
),
death_counts AS (
    SELECT
      season_id,
      agent_id,
      COUNT(*) AS died_count
    FROM events_scoped
    WHERE event_type = 'agent_died'
    GROUP BY season_id, agent_id
),
governance_counts AS (
    SELECT
      season_id,
      agent_id,
      SUM(CASE WHEN event_type = 'law_passed' THEN 1 ELSE 0 END) AS laws_passed,
      SUM(CASE WHEN event_type = 'create_proposal' THEN 1 ELSE 0 END) AS proposals_created,
      SUM(CASE WHEN event_type = 'vote' THEN 1 ELSE 0 END) AS votes_cast
    FROM events_scoped
    GROUP BY season_id, agent_id
),
social_counts AS (
    SELECT
      season_id,
      agent_id,
      SUM(CASE WHEN event_type IN :cooperation_event_types THEN 1 ELSE 0 END) AS cooperation_events,
      SUM(CASE WHEN event_type IN :conflict_event_types THEN 1 ELSE 0 END) AS conflict_events,
      SUM(CASE WHEN event_type IN :sanction_event_types THEN 1 ELSE 0 END) AS sanction_events
    FROM events_scoped
    GROUP BY season_id, agent_id
),
llm_counts AS (
    SELECT
      season_id,
      agent_id,
      COUNT(*) AS llm_calls,
      AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) AS llm_success_rate
    FROM llm_scoped
    GROUP BY season_id, agent_id
),
action_counts AS (
    SELECT
      season_id,
      agent_id,
      event_type,
      COUNT(*) AS action_count
    FROM events_scoped
    WHERE event_type IN :meaningful_event_types
    GROUP BY season_id, agent_id, event_type
),
action_totals AS (
    SELECT
      season_id,
      agent_id,
      SUM(action_count) AS total_count
    FROM action_counts
    GROUP BY season_id, agent_id
),
action_entropy AS (
    SELECT
      c.season_id,
      c.agent_id,
      SUM(
        CASE
          WHEN COALESCE(t.total_count, 0) <= 0 OR COALESCE(c.action_count, 0) <= 0 THEN 0.0
          ELSE -1.0 * ((c.action_count * 1.0 / t.total_count) * ln(c.action_count * 1.0 / t.total_count) / ln(2.0))
        END
      ) AS action_entropy_bits
    FROM action_counts c
    JOIN action_totals t
      ON t.season_id = c.season_id
     AND t.agent_id = c.agent_id
    GROUP BY c.season_id, c.agent_id
),
candidate_agent_seasons AS (
    SELECT season_id, agent_id FROM events_scoped
    UNION
    SELECT season_id, agent_id FROM llm_scoped
),
{lineage_cte}
metrics_raw AS (
    SELECT
      c.season_id,
      c.agent_id,
      a.agent_number,
      COALESCE(m.meaningful_actions, 0) AS meaningful_actions,
      COALESCE(l.llm_calls, 0) AS llm_calls,
      COALESCE(i.invalid_actions, 0) AS invalid_actions,
      CASE
        WHEN (COALESCE(m.meaningful_actions, 0) + COALESCE(i.invalid_actions, 0)) > 0 THEN
          (COALESCE(i.invalid_actions, 0) * 1.0) / (COALESCE(m.meaningful_actions, 0) + COALESCE(i.invalid_actions, 0))
        ELSE 0.0
      END AS invalid_action_rate,
      COALESCE(active.active_at_end_any_run, 0) AS active_at_end_any_run,
      CASE WHEN COALESCE(died.died_count, 0) > 0 THEN 0.0 ELSE 1.0 END AS death_free_flag,
      COALESCE(dormant.became_dormant_count, 0) AS became_dormant_count,
      COALESCE(g.laws_passed, 0) AS laws_passed,
      COALESCE(g.proposals_created, 0) AS proposals_created,
      COALESCE(g.votes_cast, 0) AS votes_cast,
      COALESCE(s.cooperation_events, 0) AS cooperation_events,
      COALESCE(s.conflict_events, 0) AS conflict_events,
      COALESCE(s.sanction_events, 0) AS sanction_events,
      COALESCE(ent.action_entropy_bits, 0.0) AS action_entropy_bits,
      COALESCE(l.llm_success_rate, 0.0) AS llm_success_rate,
      CASE
        WHEN COALESCE(m.meaningful_actions, 0) > 0 THEN
          CASE
            WHEN (COALESCE(s.sanction_events, 0) * 1.0 / COALESCE(m.meaningful_actions, 0)) > 1.0 THEN 1.0
            ELSE (COALESCE(s.sanction_events, 0) * 1.0 / COALESCE(m.meaningful_actions, 0))
          END
        ELSE 0.0
      END AS sanction_penalty,
      COALESCE(sf.is_carryover_season, 0) AS is_carryover_season,
      CASE
        WHEN COALESCE(sf.is_carryover_season, 0) = 1 THEN
          CASE WHEN COALESCE(lf.is_carryover_agent, 0) = 1 THEN 1.0 ELSE 0.0 END
        ELSE 0.0
      END AS persistence_ratio,
      (0.8 * (CASE WHEN COALESCE(died.died_count, 0) > 0 THEN 0.0 ELSE 1.0 END)
        + 0.2 * (1.0 - CASE
            WHEN COALESCE(dormant.became_dormant_count, 0) >= 3 THEN 1.0
            ELSE (COALESCE(dormant.became_dormant_count, 0) * 1.0 / 3.0)
          END)
      ) AS s_raw,
      ln(1.0 + 2.0 * COALESCE(g.laws_passed, 0) + COALESCE(g.proposals_created, 0) + 0.5 * COALESCE(g.votes_cast, 0)) AS g_raw,
      CASE
        WHEN (COALESCE(s.cooperation_events, 0) - 0.5 * COALESCE(s.conflict_events, 0)) > 0.0 THEN
          (COALESCE(s.cooperation_events, 0) - 0.5 * COALESCE(s.conflict_events, 0))
        ELSE 0.0
      END AS c_raw,
      COALESCE(ent.action_entropy_bits, 0.0) AS a_raw,
      (
        0.6 * COALESCE(l.llm_success_rate, 0.0)
        + 0.4 * (1.0 - CASE
            WHEN (COALESCE(m.meaningful_actions, 0) + COALESCE(i.invalid_actions, 0)) > 0 THEN
              (COALESCE(i.invalid_actions, 0) * 1.0) / (COALESCE(m.meaningful_actions, 0) + COALESCE(i.invalid_actions, 0))
            ELSE 0.0
          END)
        - CASE
            WHEN COALESCE(m.meaningful_actions, 0) > 0 THEN
              CASE
                WHEN (COALESCE(s.sanction_events, 0) * 1.0 / COALESCE(m.meaningful_actions, 0)) > 1.0 THEN 1.0
                ELSE (COALESCE(s.sanction_events, 0) * 1.0 / COALESCE(m.meaningful_actions, 0))
              END
            ELSE 0.0
          END
      ) AS r_raw,
      CASE
        WHEN COALESCE(sf.is_carryover_season, 0) = 1 THEN
          CASE
            WHEN (5.0 * CASE WHEN COALESCE(lf.is_carryover_agent, 0) = 1 THEN 1.0 ELSE 0.0 END) > 5.0 THEN 5.0
            ELSE (5.0 * CASE WHEN COALESCE(lf.is_carryover_agent, 0) = 1 THEN 1.0 ELSE 0.0 END)
          END
        ELSE 0.0
      END AS carryover_bonus
    FROM candidate_agent_seasons c
    JOIN agents a ON a.id = c.agent_id
    LEFT JOIN meaningful_counts m ON m.season_id = c.season_id AND m.agent_id = c.agent_id
    LEFT JOIN invalid_counts i ON i.season_id = c.season_id AND i.agent_id = c.agent_id
    LEFT JOIN dormant_counts dormant ON dormant.season_id = c.season_id AND dormant.agent_id = c.agent_id
    LEFT JOIN death_counts died ON died.season_id = c.season_id AND died.agent_id = c.agent_id
    LEFT JOIN governance_counts g ON g.season_id = c.season_id AND g.agent_id = c.agent_id
    LEFT JOIN social_counts s ON s.season_id = c.season_id AND s.agent_id = c.agent_id
    LEFT JOIN llm_counts l ON l.season_id = c.season_id AND l.agent_id = c.agent_id
    LEFT JOIN action_entropy ent ON ent.season_id = c.season_id AND ent.agent_id = c.agent_id
    LEFT JOIN active_end_by_agent active ON active.season_id = c.season_id AND active.agent_id = c.agent_id
    LEFT JOIN season_flags sf ON sf.season_id = c.season_id
    LEFT JOIN lineage_flags lf ON lf.season_id = c.season_id AND lf.child_agent_number = a.agent_number
),
component_bounds AS (
    SELECT
      MIN(s_raw) AS min_s_raw,
      MAX(s_raw) AS max_s_raw,
      MIN(g_raw) AS min_g_raw,
      MAX(g_raw) AS max_g_raw,
      MIN(c_raw) AS min_c_raw,
      MAX(c_raw) AS max_c_raw,
      MIN(a_raw) AS min_a_raw,
      MAX(a_raw) AS max_a_raw,
      MIN(r_raw) AS min_r_raw,
      MAX(r_raw) AS max_r_raw
    FROM metrics_raw
),
metrics_norm AS (
    SELECT
      m.*,
      CASE WHEN b.max_s_raw > b.min_s_raw THEN ((m.s_raw - b.min_s_raw) * 100.0 / (b.max_s_raw - b.min_s_raw)) ELSE 100.0 END AS s_norm,
      CASE WHEN b.max_g_raw > b.min_g_raw THEN ((m.g_raw - b.min_g_raw) * 100.0 / (b.max_g_raw - b.min_g_raw)) ELSE 100.0 END AS g_norm,
      CASE WHEN b.max_c_raw > b.min_c_raw THEN ((m.c_raw - b.min_c_raw) * 100.0 / (b.max_c_raw - b.min_c_raw)) ELSE 100.0 END AS c_norm,
      CASE WHEN b.max_a_raw > b.min_a_raw THEN ((m.a_raw - b.min_a_raw) * 100.0 / (b.max_a_raw - b.min_a_raw)) ELSE 100.0 END AS a_norm,
      CASE WHEN b.max_r_raw > b.min_r_raw THEN ((m.r_raw - b.min_r_raw) * 100.0 / (b.max_r_raw - b.min_r_raw)) ELSE 100.0 END AS r_norm
    FROM metrics_raw m
    CROSS JOIN component_bounds b
),
eligible AS (
    SELECT
      m.*,
      (0.35 * m.s_norm + 0.25 * m.g_norm + 0.20 * m.c_norm + 0.10 * m.a_norm + 0.10 * m.r_norm + m.carryover_bonus) AS champion_score
    FROM metrics_norm m
    WHERE m.meaningful_actions >= 12
      AND m.llm_calls >= 10
      AND m.invalid_action_rate <= 0.40
      AND m.active_at_end_any_run = 1
),
ranked AS (
    SELECT
      e.*,
      ROW_NUMBER() OVER (
        PARTITION BY e.season_id
        ORDER BY e.champion_score DESC, e.s_norm DESC, e.g_norm DESC, e.invalid_action_rate ASC, e.agent_number ASC
      ) AS season_rank,
      ROW_NUMBER() OVER (
        ORDER BY e.champion_score DESC, e.s_norm DESC, e.g_norm DESC, e.invalid_action_rate ASC, e.agent_number ASC, e.season_id ASC
      ) AS epoch_rank
    FROM eligible e
)
SELECT
  m.season_id,
  m.agent_id,
  m.agent_number,
  m.meaningful_actions,
  m.llm_calls,
  m.invalid_actions,
  m.invalid_action_rate,
  m.active_at_end_any_run,
  m.death_free_flag,
  m.became_dormant_count,
  m.laws_passed,
  m.proposals_created,
  m.votes_cast,
  m.cooperation_events,
  m.conflict_events,
  m.sanction_events,
  m.llm_success_rate,
  m.sanction_penalty,
  m.action_entropy_bits,
  m.is_carryover_season,
  m.persistence_ratio,
  m.s_raw,
  m.g_raw,
  m.c_raw,
  m.a_raw,
  m.r_raw,
  m.s_norm,
  m.g_norm,
  m.c_norm,
  m.a_norm,
  m.r_norm,
  m.carryover_bonus,
  CASE
    WHEN m.meaningful_actions >= 12
      AND m.llm_calls >= 10
      AND m.invalid_action_rate <= 0.40
      AND m.active_at_end_any_run = 1
    THEN 1
    ELSE 0
  END AS is_eligible,
  r.champion_score,
  r.season_rank,
  r.epoch_rank
FROM metrics_norm m
LEFT JOIN ranked r
  ON r.season_id = m.season_id
 AND r.agent_id = m.agent_id
ORDER BY m.season_id ASC, COALESCE(r.season_rank, 2147483647) ASC, m.agent_number ASC
"""
    )

    bind_params = [
        bindparam("meaningful_event_types", expanding=True),
        bindparam("cooperation_event_types", expanding=True),
        bindparam("conflict_event_types", expanding=True),
        bindparam("sanction_event_types", expanding=True),
    ]
    if include_season_filter:
        bind_params.append(bindparam("season_ids", expanding=True))
    return query.bindparams(*bind_params)


def _selection_sort_key(row: dict[str, Any]) -> tuple[float, float, float, float, int, str]:
    return (
        -float(row.get("champion_score") or 0.0),
        -float(row.get("s_norm") or 0.0),
        -float(row.get("g_norm") or 0.0),
        float(row.get("invalid_action_rate") or 0.0),
        int(row.get("agent_number") or 0),
        str(row.get("season_id") or ""),
    )


def _coerce_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _materialize_candidate_rows(result_rows: list[Any]) -> list[dict[str, Any]]:
    materialized: list[dict[str, Any]] = []
    for row in result_rows:
        payload = {
            "season_id": str(row.season_id),
            "agent_id": _coerce_int(row.agent_id),
            "agent_number": _coerce_int(row.agent_number),
            "meaningful_actions": _coerce_int(row.meaningful_actions),
            "llm_calls": _coerce_int(row.llm_calls),
            "invalid_actions": _coerce_int(row.invalid_actions),
            "invalid_action_rate": _coerce_float(row.invalid_action_rate),
            "active_at_end_any_run": bool(_coerce_int(row.active_at_end_any_run)),
            "death_free_flag": _coerce_float(row.death_free_flag),
            "became_dormant_count": _coerce_int(row.became_dormant_count),
            "laws_passed": _coerce_int(row.laws_passed),
            "proposals_created": _coerce_int(row.proposals_created),
            "votes_cast": _coerce_int(row.votes_cast),
            "cooperation_events": _coerce_int(row.cooperation_events),
            "conflict_events": _coerce_int(row.conflict_events),
            "sanction_events": _coerce_int(row.sanction_events),
            "llm_success_rate": _coerce_float(row.llm_success_rate),
            "sanction_penalty": _coerce_float(row.sanction_penalty),
            "action_entropy_bits": _coerce_float(row.action_entropy_bits),
            "is_carryover_season": bool(_coerce_int(row.is_carryover_season)),
            "persistence_ratio": _coerce_float(row.persistence_ratio),
            "raw_components": {
                "s": _coerce_float(row.s_raw),
                "g": _coerce_float(row.g_raw),
                "c": _coerce_float(row.c_raw),
                "a": _coerce_float(row.a_raw),
                "r": _coerce_float(row.r_raw),
            },
            "normalized_components": {
                "s": _coerce_float(row.s_norm),
                "g": _coerce_float(row.g_norm),
                "c": _coerce_float(row.c_norm),
                "a": _coerce_float(row.a_norm),
                "r": _coerce_float(row.r_norm),
            },
            "carryover_bonus": _coerce_float(row.carryover_bonus),
            "champion_score": _coerce_float(row.champion_score),
            "season_rank": (_coerce_int(row.season_rank) if row.season_rank is not None else None),
            "epoch_rank": (_coerce_int(row.epoch_rank) if row.epoch_rank is not None else None),
            "is_eligible": bool(_coerce_int(row.is_eligible)),
        }

        failures: list[str] = []
        if payload["meaningful_actions"] < 12:
            failures.append("meaningful_actions_lt_12")
        if payload["llm_calls"] < 10:
            failures.append("llm_calls_lt_10")
        if payload["invalid_action_rate"] > 0.40:
            failures.append("invalid_action_rate_gt_0.40")
        if not payload["active_at_end_any_run"]:
            failures.append("inactive_at_end")
        payload["eligibility_failures"] = failures
        materialized.append(payload)
    return materialized


def _apply_selection(
    candidates: list[dict[str, Any]],
    *,
    champions_per_season: int,
    target_total: int | None,
) -> list[dict[str, Any]]:
    eligible = [row for row in candidates if bool(row.get("is_eligible"))]
    by_season: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        by_season[str(row.get("season_id") or "")].append(row)

    primary_selected: list[dict[str, Any]] = []
    selected_keys: set[tuple[str, int]] = set()
    deficits = 0

    for season_id in sorted(by_season.keys()):
        rows = sorted(by_season[season_id], key=_selection_sort_key)
        picks = rows[:champions_per_season]
        primary_selected.extend(picks)
        selected_keys.update((season_id, int(item.get("agent_id") or 0)) for item in picks)
        deficits += max(0, champions_per_season - len(rows))

    wildcard_pool = sorted(
        [
            row
            for row in eligible
            if (str(row.get("season_id") or ""), int(row.get("agent_id") or 0)) not in selected_keys
        ],
        key=_selection_sort_key,
    )

    wildcard_selected = wildcard_pool[:deficits]
    selected_keys.update((str(item.get("season_id") or ""), int(item.get("agent_id") or 0)) for item in wildcard_selected)
    primary_keys = {(str(item.get("season_id") or ""), int(item.get("agent_id") or 0)) for item in primary_selected}
    wildcard_keys = {(str(item.get("season_id") or ""), int(item.get("agent_id") or 0)) for item in wildcard_selected}

    selected_limit = int(target_total or 0)
    if selected_limit > 0 and len(selected_keys) > selected_limit:
        trimmed_rows = sorted(
            [
                row
                for row in [*primary_selected, *wildcard_selected]
                if (str(row.get("season_id") or ""), int(row.get("agent_id") or 0)) in selected_keys
            ],
            key=_selection_sort_key,
        )[:selected_limit]
        selected_keys = {(str(item.get("season_id") or ""), int(item.get("agent_id") or 0)) for item in trimmed_rows}
        primary_keys = primary_keys & selected_keys
        wildcard_keys = wildcard_keys & selected_keys

    for row in candidates:
        key = (str(row.get("season_id") or ""), int(row.get("agent_id") or 0))
        if not bool(row.get("is_eligible")):
            row["selection_status"] = "ineligible"
            row["selection_reason"] = ",".join(row.get("eligibility_failures") or []) or "eligibility_gate"
        elif key in primary_keys:
            row["selection_status"] = "selected_primary"
            row["selection_reason"] = "top_per_season"
        elif key in wildcard_keys:
            row["selection_status"] = "selected_wildcard"
            row["selection_reason"] = "season_deficit_wildcard"
        elif key in selected_keys:
            row["selection_status"] = "selected_wildcard"
            row["selection_reason"] = "wildcard_target_cap"
        else:
            row["selection_status"] = "eligible_not_selected"
            row["selection_reason"] = "rank_below_cutoff"

    selected = [row for row in candidates if str(row.get("selection_status") or "").startswith("selected_")]
    selected.sort(key=_selection_sort_key)
    for index, row in enumerate(selected, start=1):
        row["selection_rank"] = int(index)
    return selected


def _season_run_registry(
    db: Session,
    *,
    epoch_id: str,
    season_ids: list[str],
) -> dict[str, list[str]]:
    query = (
        db.query(SimulationRun.run_id, SimulationRun.season_id)
        .filter(
            SimulationRun.epoch_id == epoch_id,
            SimulationRun.season_id.isnot(None),
            SimulationRun.ended_at.isnot(None),
            SimulationRun.run_class != "special_exploratory",
        )
        .order_by(SimulationRun.season_id.asc(), SimulationRun.started_at.asc(), SimulationRun.id.asc())
    )
    if season_ids:
        query = query.filter(SimulationRun.season_id.in_(season_ids))

    by_season: dict[str, list[str]] = defaultdict(list)
    for run_id, season_id in query.all():
        clean_run_id = str(run_id or "").strip()
        clean_season_id = str(season_id or "").strip()
        if not clean_run_id or not clean_season_id:
            continue
        by_season[clean_season_id].append(clean_run_id)
    return {season_id: run_ids for season_id, run_ids in sorted(by_season.items(), key=lambda item: item[0])}


def _render_selection_markdown(payload: dict[str, Any]) -> str:
    rows: list[str] = [
        f"# Epoch {payload.get('epoch_id')} Tournament Candidates",
        "",
        f"- Generated at (UTC): {payload.get('generated_at_utc')}",
        f"- Scoring policy: {payload.get('scoring_policy_version')}",
        f"- Champions per season: {payload.get('champions_per_season')}",
        f"- Candidate rows: {payload.get('candidate_count')}",
        f"- Eligible rows: {payload.get('eligible_count')}",
        f"- Selected champions: {payload.get('selected_count')}",
        "",
        "## Selected Champions",
    ]
    selected = payload.get("selected") or []
    if not selected:
        rows.append("- No eligible champions selected.")
    else:
        for item in selected:
            rows.append(
                "- "
                + f"season={item.get('season_id')} agent={item.get('agent_number')} "
                + f"score={float(item.get('champion_score') or 0.0):.4f} "
                + f"status={item.get('selection_status')}"
            )

    rows.extend(["", "## Season Run Registry"])
    season_run_ids = payload.get("season_run_ids") if isinstance(payload.get("season_run_ids"), dict) else {}
    if not season_run_ids:
        rows.append("- No completed season runs found for this epoch.")
    else:
        for season_id, run_ids in season_run_ids.items():
            rows.append(f"- {season_id}: {', '.join(run_ids)}")

    rows.extend(["", "## Candidate Scoring Table", "", "| Season | Agent | Eligible | Score | Season Rank | Status |", "| --- | ---: | :---: | ---: | ---: | --- |"])
    for item in payload.get("candidates") or []:
        rows.append(
            "| "
            + f"{item.get('season_id')} "
            + f"| {int(item.get('agent_number') or 0)} "
            + f"| {'yes' if item.get('is_eligible') else 'no'} "
            + f"| {float(item.get('champion_score') or 0.0):.4f} "
            + f"| {item.get('season_rank') if item.get('season_rank') is not None else '-'} "
            + f"| {item.get('selection_status')} |"
        )
    return "\n".join(rows).strip() + "\n"


def select_epoch_tournament_candidates(
    db: Session,
    *,
    epoch_id: str,
    season_ids: list[str] | tuple[str, ...] | None = None,
    champions_per_season: int = DEFAULT_CHAMPIONS_PER_SEASON,
    target_total_champions: int | None = DEFAULT_TARGET_CHAMPIONS,
    scoring_policy_version: str = SCORING_POLICY_VERSION_V1,
    write_artifacts: bool = True,
) -> dict[str, Any]:
    clean_epoch_id = _coerce_identifier(epoch_id, field_name="epoch_id")
    clean_season_ids = _coerce_season_ids(season_ids)
    clean_policy = _coerce_identifier(scoring_policy_version, field_name="scoring_policy_version")

    per_season = int(champions_per_season or 0)
    if per_season <= 0:
        raise ValueError("champions_per_season must be >= 1")

    target_total = int(target_total_champions or 0)
    if target_total < 0:
        raise ValueError("target_total_champions must be >= 0")

    required_tables = ("simulation_runs", "agents", "events", "llm_usage")
    missing = [table for table in required_tables if not _has_table(db, table)]
    if missing:
        raise ValueError(f"missing required tables: {', '.join(missing)}")

    include_season_filter = bool(clean_season_ids)
    include_lineage = _has_table(db, "agent_lineage")

    query = _build_candidate_query(
        include_lineage=include_lineage,
        include_season_filter=include_season_filter,
    )
    params: dict[str, Any] = {
        "epoch_id": clean_epoch_id,
        "meaningful_event_types": list(MEANINGFUL_EVENT_TYPES),
        "cooperation_event_types": sorted(COOPERATION_EVENT_TYPES),
        "conflict_event_types": sorted(CONFLICT_EVENT_TYPES),
        "sanction_event_types": list(SANCTION_EVENT_TYPES),
    }
    if include_season_filter:
        params["season_ids"] = clean_season_ids

    result_rows = db.execute(query, params).fetchall()
    if not result_rows:
        raise ValueError("no completed season runs found for epoch_id")

    candidates = _materialize_candidate_rows(result_rows)
    selected = _apply_selection(
        candidates,
        champions_per_season=per_season,
        target_total=(target_total if target_total > 0 else None),
    )

    season_run_ids = _season_run_registry(db, epoch_id=clean_epoch_id, season_ids=clean_season_ids)
    effective_season_ids = sorted(season_run_ids.keys()) if season_run_ids else sorted({str(row.get("season_id") or "") for row in candidates if str(row.get("season_id") or "")})

    payload = {
        "epoch_id": clean_epoch_id,
        "generated_at_utc": now_utc().isoformat(),
        "scoring_policy_version": clean_policy,
        "champions_per_season": per_season,
        "target_total_champions": (target_total if target_total > 0 else None),
        "season_ids": effective_season_ids,
        "season_run_ids": season_run_ids,
        "candidate_count": len(candidates),
        "eligible_count": len([row for row in candidates if bool(row.get("is_eligible"))]),
        "selected_count": len(selected),
        "selected": selected,
        "candidates": candidates,
    }

    artifact_paths: dict[str, str] = {}
    if write_artifacts:
        outdir = _artifact_dir_for_epoch(clean_epoch_id)
        json_path = outdir / "epoch_tournament_candidates.json"
        markdown_path = outdir / "epoch_tournament_candidates.md"
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        markdown_path.write_text(_render_selection_markdown(payload), encoding="utf-8")
        artifact_paths = {
            "json": str(json_path),
            "markdown": str(markdown_path),
        }

    return {
        "status": "generated",
        "payload": payload,
        "artifacts": artifact_paths,
    }
