

from __future__ import annotations

from typing import Any

from . import BaseAgent

class TravelAgent(BaseAgent):

    agent_name = "travel_agent"

    def health_check(self) -> dict[str, Any]:
        return {"agent": self.agent_name, "type": "travel", "status": "ready", "capabilities": ["itinerary_builder", "trip_budget", "packing_list", "disruption_response"]}

    def handle_itinerary_builder(self, destination: str = "", days: int = 0, **kw: Any) -> dict[str, Any]:
        if not destination:
            raise ValueError("'destination' is required")
        return {"message": "Built itinerary", "destination": destination, "days": days, "plan": [{"day": i, "focus": "arrival" if i == 1 else "activities"} for i in range(1, max(days, 1) + 1)]}

    def handle_trip_budget(self, flights: float = 0.0, hotel: float = 0.0, food: float = 0.0, local_transport: float = 0.0, **kw: Any) -> dict[str, Any]:
        total = round(flights + hotel + food + local_transport, 2)
        return {"message": "Calculated trip budget", "total": total}

    def handle_packing_list(self, trip_type: str = "", weather: str = "", **kw: Any) -> dict[str, Any]:
        items = ["documents", "charger", "toiletries"]
        if "cold" in weather.lower():
            items.append("jacket")
        if "business" in trip_type.lower():
            items.append("formal outfit")
        return {"message": "Generated packing list", "items": items}

    def handle_disruption_response(self, issue: str = "", **kw: Any) -> dict[str, Any]:
        return {"message": "Prepared travel disruption response", "issue": issue, "actions": ["check carrier options", "rebook essentials", "notify stakeholders"]}
