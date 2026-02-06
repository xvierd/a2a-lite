"""
Example 14: Multi-Agent Network Orchestration

Demonstrates using AgentNetwork to manage and delegate to multiple agents.
One "planner" agent coordinates between specialized agents.

Run:
    # Start the specialized agents first (in separate terminals):
    # Terminal 1: python examples/14_multi_agent_network.py weather
    # Terminal 2: python examples/14_multi_agent_network.py hotel
    # Terminal 3: python examples/14_multi_agent_network.py planner
"""
import sys
from a2a_lite import Agent
from a2a_lite.orchestration import AgentNetwork


def create_weather_agent():
    """A simple weather agent."""
    agent = Agent(
        name="Weather Agent",
        description="Provides weather forecasts",
    )

    @agent.skill("forecast", description="Get weather forecast for a city")
    async def forecast(city: str) -> dict:
        # Simulated weather data
        forecasts = {
            "NYC": {"temp": "72F", "condition": "Sunny", "humidity": "45%"},
            "London": {"temp": "58F", "condition": "Cloudy", "humidity": "75%"},
            "Tokyo": {"temp": "80F", "condition": "Humid", "humidity": "85%"},
        }
        return forecasts.get(city, {"temp": "N/A", "condition": "Unknown"})

    return agent


def create_hotel_agent():
    """A simple hotel search agent."""
    agent = Agent(
        name="Hotel Agent",
        description="Searches for hotels",
    )

    @agent.skill("search", description="Search hotels in a city")
    async def search(city: str, budget: str = "medium") -> dict:
        # Simulated hotel data
        return {
            "city": city,
            "hotels": [
                {"name": f"Grand {city} Hotel", "price": "$200/night", "rating": 4.5},
                {"name": f"{city} Inn", "price": "$120/night", "rating": 4.0},
            ],
        }

    return agent


def create_planner_agent():
    """A planner agent that delegates to weather and hotel agents."""
    network = AgentNetwork()
    network.add("weather", "http://localhost:8787")
    network.add("hotels", "http://localhost:8788")

    agent = Agent(
        name="Trip Planner",
        description="Plans trips by coordinating weather and hotel agents",
        network=network,
    )

    @agent.skill("plan_trip", description="Plan a trip to a destination")
    async def plan_trip(destination: str) -> dict:
        # Delegate to specialized agents
        weather = await agent.delegate("weather", "forecast", city=destination)
        hotels = await agent.delegate("hotels", "search", city=destination)

        return {
            "destination": destination,
            "weather": weather,
            "hotels": hotels,
            "recommendation": f"Great time to visit {destination}!",
        }

    @agent.skill("compare", description="Compare weather across cities")
    async def compare(cities: str) -> dict:
        city_list = [c.strip() for c in cities.split(",")]
        results = {}
        for city in city_list:
            results[city] = await agent.delegate("weather", "forecast", city=city)
        return results

    return agent


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "planner"

    if role == "weather":
        create_weather_agent().run(port=8787)
    elif role == "hotel":
        create_hotel_agent().run(port=8788)
    else:
        create_planner_agent().run(port=8789)
