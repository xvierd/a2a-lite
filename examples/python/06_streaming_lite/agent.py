"""
Streaming Agent - A2A Lite Implementation

Demonstrates real-time streaming with a single decorator parameter.
Compare this ~50 line implementation with the ~364 line Google SDK version.
"""

import asyncio
import random
from a2a_lite import Agent

agent = Agent(
    name="StreamingAgent",
    description="Agent with real-time streaming capabilities",
    version="1.0.0"
)


@agent.skill("chat", streaming=True)
async def chat(message: str):
    """
    Chat with word-by-word streaming response.
    
    Just use 'yield' instead of 'return' and A2A Lite handles SSE!
    """
    responses = [
        f"You said '{message}' - that's interesting!",
        f"I understand: '{message}'. Let me respond...",
        f"Regarding '{message}', here's my perspective...",
    ]
    response = random.choice(responses)
    
    # Stream word by word
    words = response.split()
    for i, word in enumerate(words):
        await asyncio.sleep(0.1)  # Simulate processing
        
        yield {
            "token": word + ("" if i == len(words) - 1 else " "),
            "index": i,
            "is_last": i == len(words) - 1
        }


@agent.skill("count", streaming=True)
async def count(start: int = 1, end: int = 10):
    """
    Count from start to end with progress updates.
    """
    total = end - start + 1
    
    for i, num in enumerate(range(start, end + 1)):
        await asyncio.sleep(0.3)
        
        yield {
            "number": num,
            "progress": {
                "current": i + 1,
                "total": total,
                "percentage": round((i + 1) / total * 100, 1)
            }
        }


@agent.skill("story", streaming=True)
async def story(theme: str = "adventure"):
    """
    Generate a story progressively.
    """
    stories = {
        "adventure": [
            "Once upon a time,",
            "a brave explorer set out",
            "on a journey to find",
            "the legendary Crystal Mountain.",
            "They finally reached the summit",
            "and discovered the treasure within."
        ],
        "mystery": [
            "The old mansion stood silent,",
            "its windows dark and empty.",
            "Detective Miller approached slowly,",
            "his flashlight cutting through the fog.",
            "Inside, a clue awaited",
            "that would solve the case."
        ]
    }
    
    parts = stories.get(theme, stories["adventure"])
    
    for i, part in enumerate(parts):
        await asyncio.sleep(0.4)
        yield {
            "part": part,
            "part_number": i + 1,
            "total_parts": len(parts)
        }


@agent.skill("progress", streaming=True)
async def progress(task: str = "processing"):
    """
    Simulate a long-running task with progress updates.
    """
    stages = [
        ("Initializing", 10),
        ("Loading data", 30),
        ("Processing", 60),
        ("Analyzing results", 85),
        ("Finalizing", 100)
    ]
    
    for stage_name, percent in stages:
        await asyncio.sleep(0.5)
        yield {
            "task": task,
            "stage": stage_name,
            "progress": percent,
            "status": "working" if percent < 100 else "complete"
        }


if __name__ == "__main__":
    print("=" * 70)
    print("Streaming Agent - A2A Lite")
    print("=" * 70)
    print("Agent: StreamingAgent")
    print("Port: 8791")
    print("-" * 70)
    print("Streaming Skills (use streaming=True decorator):")
    print("  - chat: Word-by-word responses")
    print("  - count: Number stream with progress")
    print("  - story: Progressive story generation")
    print("  - progress: Task progress simulation")
    print("-" * 70)
    print("A2A Lite handles:")
    print("  ✓ SSE protocol formatting")
    print("  ✓ Connection keep-alive")
    print("  ✓ Chunk encoding/decoding")
    print("  ✓ Streaming error handling")
    print("-" * 70)
    print("Test with:")
    print('  curl -N -H "Accept: text/event-stream" -X POST ...')
    print("=" * 70)
    
    agent.run(port=8791)
