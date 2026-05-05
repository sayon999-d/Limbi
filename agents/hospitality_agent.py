

from __future__ import annotations

from typing import Any

from agents import BaseAgent

class HospitalityAgent(BaseAgent):

    agent_name = "hospitality_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "hospitality", "status": "ready", "capabilities": ["guest_itinerary", "service_recovery", "occupancy_summary", "staffing_plan"]}

    def handle_guest_itinerary(self, guest_type: str = "", nights: int = 1, **kw: Any) -> dict[str, Any]:
        return {"message": "Built guest itinerary", "guest_type": guest_type, "nights": nights, "touchpoints": ["check-in", "stay support", "check-out"]}

    def handle_service_recovery(self, issue: str = "", severity: str = "medium", **kw: Any) -> dict[str, Any]:
        return {"message": "Prepared service recovery plan", "issue": issue, "action": "manager follow-up" if severity == "high" else "front desk resolution"}

    def handle_occupancy_summary(self, rooms: int = 0, occupied: int = 0, **kw: Any) -> dict[str, Any]:
        rate = round((occupied / rooms) * 100, 2) if rooms else 0
        return {"message": "Summarized occupancy", "occupancy_percent": rate}

    def handle_staffing_plan(self, shift: str = "", occupancy_percent: float = 0.0, **kw: Any) -> dict[str, Any]:
        staff_level = "high" if occupancy_percent >= 80 else "normal"
        return {"message": "Created staffing plan", "shift": shift, "staff_level": staff_level}
