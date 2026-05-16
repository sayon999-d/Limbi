

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections import defaultdict
from typing import Any

from agents import BaseAgent

logger = logging.getLogger("limbi.agents.learning")

_LEARN_DB = os.getenv("LEARNING_DB_PATH", "./limbi_learning.db")
_lock = threading.Lock()

ALPHA = 0.1
GAMMA = 0.9
EPSILON = 0.15

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_LEARN_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _init_learn_db() -> None:
    with _lock:
        conn = _get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS q_table (
                state       TEXT NOT NULL,
                action      TEXT NOT NULL,
                q_value     REAL DEFAULT 0.0,
                visits      INTEGER DEFAULT 0,
                avg_reward  REAL DEFAULT 0.0,
                last_update TEXT,
                PRIMARY KEY (state, action)
            );

            CREATE TABLE IF NOT EXISTS feedback_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                state       TEXT NOT NULL,
                action      TEXT NOT NULL,
                reward      REAL NOT NULL,
                next_state  TEXT DEFAULT '',
                context     TEXT DEFAULT '{}'
            );
        """)
        conn.commit()
        conn.close()

_init_learn_db()

class LearningAgent(BaseAgent):

    agent_name = "learning_agent"

    def health_check(self) -> dict[str, Any]:
        with _lock:
            conn = _get_conn()
            q_count = conn.execute("SELECT COUNT(*) FROM q_table").fetchone()[0]
            feedback_count = conn.execute("SELECT COUNT(*) FROM feedback_log").fetchone()[0]
            conn.close()
        return {
            "agent": self.agent_name,
            "type": "reinforcement_learning",
            "status": "ready",
            "q_table_entries": q_count,
            "feedback_entries": feedback_count,
            "hyperparameters": {
                "alpha": ALPHA, "gamma": GAMMA, "epsilon": EPSILON,
            },
        }

    def handle_get_best_action(
        self,
        state: str = "",
        available_actions: list[str] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        if not state:
            state = str(
                kw.get("query_category")
                or kw.get("category")
                or kw.get("topic")
                or kw.get("current_goal")
                or "general"
            ).strip() or "general"

        import random

        with _lock:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT action, q_value, visits FROM q_table WHERE state = ? ORDER BY q_value DESC",
                (state,),
            ).fetchall()
            conn.close()

        known_actions = {r["action"]: {"q_value": r["q_value"], "visits": r["visits"]} for r in rows}

        if random.random() < EPSILON and available_actions:

            chosen = random.choice(available_actions)
            return {
                "state": state,
                "action": chosen,
                "q_value": known_actions.get(chosen, {}).get("q_value", 0.0),
                "mode": "exploration",
                "all_q_values": known_actions,
            }

        if known_actions:
            best = max(known_actions, key=lambda a: known_actions[a]["q_value"])
            return {
                "state": state,
                "action": best,
                "q_value": known_actions[best]["q_value"],
                "visits": known_actions[best]["visits"],
                "mode": "exploitation",
                "all_q_values": known_actions,
            }

        return {
            "state": state,
            "action": available_actions[0] if available_actions else "unknown",
            "q_value": 0.0,
            "mode": "no_data",
            "message": "No Q-values learned for this state yet",
        }

    def handle_teach(self, state: str = "", **kw: Any) -> dict[str, Any]:

        return self.handle_get_insights()

    def handle_record_feedback(
        self,
        state: str = "",
        action: str = "",
        reward: float = 0.0,
        next_state: str = "",
        context: dict[str, Any] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:

        if not state or not action:
            raise ValueError("Both 'state' and 'action' are required")

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        with _lock:
            conn = _get_conn()

            row = conn.execute(
                "SELECT q_value, visits, avg_reward FROM q_table WHERE state = ? AND action = ?",
                (state, action),
            ).fetchone()

            old_q = row["q_value"] if row else 0.0
            visits = (row["visits"] if row else 0) + 1
            old_avg = row["avg_reward"] if row else 0.0

            max_next_q = 0.0
            if next_state:
                next_row = conn.execute(
                    "SELECT MAX(q_value) as max_q FROM q_table WHERE state = ?",
                    (next_state,),
                ).fetchone()
                max_next_q = next_row["max_q"] or 0.0

            new_q = old_q + ALPHA * (reward + GAMMA * max_next_q - old_q)
            new_avg = old_avg + (reward - old_avg) / visits

            conn.execute("""
                INSERT INTO q_table (state, action, q_value, visits, avg_reward, last_update)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(state, action) DO UPDATE SET
                    q_value = ?, visits = ?, avg_reward = ?, last_update = ?
            """, (state, action, new_q, visits, new_avg, now,
                  new_q, visits, new_avg, now))

            conn.execute(
                "INSERT INTO feedback_log (timestamp, state, action, reward, next_state, context) VALUES (?, ?, ?, ?, ?, ?)",
                (now, state, action, reward, next_state, json.dumps(context or {})),
            )

            conn.commit()
            conn.close()

        return {
            "message": f"Q({state}, {action}) updated: {old_q:.3f} -> {new_q:.3f}",
            "state": state,
            "action": action,
            "reward": reward,
            "old_q": round(old_q, 3),
            "new_q": round(new_q, 3),
            "visits": visits,
            "avg_reward": round(new_avg, 3),
        }

    def handle_get_q_table(self, state: str = "", **kw: Any) -> dict[str, Any]:

        with _lock:
            conn = _get_conn()
            if state:
                rows = conn.execute(
                    "SELECT * FROM q_table WHERE state = ? ORDER BY q_value DESC", (state,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM q_table ORDER BY state, q_value DESC"
                ).fetchall()
            conn.close()

        entries: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            entries[r["state"]].append({
                "action": r["action"],
                "q_value": round(r["q_value"], 3),
                "visits": r["visits"],
                "avg_reward": round(r["avg_reward"], 3),
            })

        return {
            "q_table": dict(entries),
            "total_entries": len(rows),
            "states_tracked": len(entries),
        }

    def handle_get_insights(self, **kw: Any) -> dict[str, Any]:

        with _lock:
            conn = _get_conn()

            best = conn.execute(
                "SELECT state, action, q_value, visits FROM q_table ORDER BY q_value DESC LIMIT 5"
            ).fetchall()

            worst = conn.execute(
                "SELECT state, action, q_value, visits FROM q_table WHERE visits >= 3 ORDER BY q_value ASC LIMIT 5"
            ).fetchall()

            most_explored = conn.execute(
                "SELECT state, action, visits FROM q_table ORDER BY visits DESC LIMIT 5"
            ).fetchall()

            recent_rewards = conn.execute(
                "SELECT reward FROM feedback_log ORDER BY id DESC LIMIT 20"
            ).fetchall()
            conn.close()

        recent_avg = sum(r["reward"] for r in recent_rewards) / max(len(recent_rewards), 1)

        return {
            "best_performing": [
                {"state": r["state"], "action": r["action"], "q": round(r["q_value"], 3)} for r in best
            ],
            "worst_performing": [
                {"state": r["state"], "action": r["action"], "q": round(r["q_value"], 3)} for r in worst
            ],
            "most_explored": [
                {"state": r["state"], "action": r["action"], "visits": r["visits"]} for r in most_explored
            ],
            "recent_reward_trend": round(recent_avg, 3),
            "recommendation": "increase_exploration" if recent_avg < 0.3 else "maintain_strategy" if recent_avg < 0.7 else "exploit_best",
        }
