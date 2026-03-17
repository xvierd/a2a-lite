"""
Streaming Skills - Google A2A SDK Implementation

Async generator functions that yield partial results for real-time streaming.

Each skill is an async generator that yields chunks of data. These chunks
are sent as Server-Sent Events (SSE) through the A2A event queue.
"""

import asyncio
import random
from typing import AsyncGenerator, Dict, Any


async def chat_stream(message: str) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Simulate a chatbot response, streaming word by word.
    
    Args:
        message: User message to respond to
        
    Yields:
        Dict with chunk type, content, and metadata
        
    Example output chunks:
        {"type": "token", "content": "Hello ", "index": 0, "is_last": false}
        {"type": "token", "content": "there!", "index": 1, "is_last": true}
        {"type": "done"}
    """
    # Generate contextual responses
    responses = [
        f"You said: '{message}'. That's interesting! Let me share my thoughts on that...",
        f"I understand: '{message}'. Here's what I think about it...",
        f"Regarding '{message}', I have some thoughts to share with you...",
        f"Thanks for sharing: '{message}'. Let me respond...",
    ]
    response = random.choice(responses)
    
    # Stream word by word
    words = response.split()
    for i, word in enumerate(words):
        await asyncio.sleep(0.15)  # Simulate processing delay
        
        is_last = (i == len(words) - 1)
        yield {
            "type": "token",
            "content": word + ("" if is_last else " "),
            "index": i,
            "is_last": is_last,
            "timestamp": asyncio.get_event_loop().time()
        }
    
    # Final done marker
    yield {"type": "done", "skill": "chat"}


async def count_stream(
    start: int, 
    end: int, 
    delay: float = 0.5
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Count from start to end, streaming each number with progress info.
    
    Args:
        start: Starting number
        end: Ending number
        delay: Delay between numbers in seconds
        
    Yields:
        Dict with number value and progress information
        
    Example output chunks:
        {"type": "number", "value": 1, "progress": {"current": 1, "total": 5, "percentage": 20.0}}
        {"type": "done", "final_count": 5}
    """
    total = end - start + 1
    
    for i, num in enumerate(range(start, end + 1)):
        await asyncio.sleep(delay)
        
        yield {
            "type": "number",
            "value": num,
            "progress": {
                "current": i + 1,
                "total": total,
                "percentage": round((i + 1) / total * 100, 1)
            },
            "timestamp": asyncio.get_event_loop().time()
        }
    
    yield {
        "type": "done", 
        "skill": "count",
        "final_count": total,
        "range": [start, end]
    }


async def story_generator(theme: str = "adventure") -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generate a short story progressively, yielding one part at a time.
    
    Args:
        theme: Story theme (adventure, mystery, sci-fi, fantasy)
        
    Yields:
        Dict with story part content and metadata
        
    Example output chunks:
        {"type": "story_part", "content": "Once upon a time...", "part_number": 1, "total_parts": 7}
        {"type": "done", "theme": "adventure", "total_parts": 7}
    """
    stories = {
        "adventure": [
            "Once upon a time, in a land far away,",
            "a brave explorer named Alex set out",
            "on a daring journey to find",
            "the legendary Crystal Mountain.",
            "After many days of treacherous travel,",
            "they finally reached the summit",
            "and discovered the ancient treasure within."
        ],
        "mystery": [
            "The old mansion stood silent in the moonlight,",
            "its windows dark and empty like hollow eyes.",
            "Detective Miller approached slowly,",
            "his flashlight cutting through the thick fog.",
            "Inside, a mysterious clue awaited",
            "that would finally solve the case",
            "and reveal the shocking truth."
        ],
        "sci-fi": [
            "In the year 2157, humanity had colonized Mars.",
            "Dr. Chen piloted her spacecraft",
            "toward the red planet's mysterious surface.",
            "What she discovered there",
            "would change everything we knew",
            "about life in the universe",
            "and humanity's place among the stars."
        ],
        "fantasy": [
            "In the realm of Eldoria, magic flowed like rivers.",
            "A young wizard named Lyra discovered",
            "an ancient spellbook hidden deep",
            "within the Crystal Caves of Doom.",
            "With great courage and wisdom,",
            "she mastered the powerful spells",
            "and saved the kingdom from darkness."
        ]
    }
    
    # Default to adventure if theme not found
    story_parts = stories.get(theme, stories["adventure"])
    
    for i, part in enumerate(story_parts):
        await asyncio.sleep(0.4)  # Dramatic pause between parts
        
        yield {
            "type": "story_part",
            "content": part,
            "part_number": i + 1,
            "total_parts": len(story_parts),
            "theme": theme,
            "timestamp": asyncio.get_event_loop().time()
        }
    
    yield {
        "type": "done",
        "skill": "story",
        "theme": theme,
        "total_parts": len(story_parts)
    }


async def progress_simulator(task: str = "processing") -> AsyncGenerator[Dict[str, Any], None]:
    """
    Simulate a long-running task with detailed progress updates.
    
    Args:
        task: Task name/description
        
    Yields:
        Dict with progress updates and stage information
        
    Example output chunks:
        {"type": "progress", "task": "processing", "stage": "Initializing", "progress": 10}
        {"type": "done", "task": "processing", "result": "processing completed successfully!"}
    """
    stages = [
        ("Initializing", 10),
        ("Loading configuration", 25),
        ("Connecting to services", 40),
        ("Processing data", 60),
        ("Analyzing results", 80),
        ("Finalizing output", 95),
        ("Complete", 100)
    ]
    
    for stage_name, progress in stages:
        await asyncio.sleep(0.6)  # Simulate work
        
        yield {
            "type": "progress",
            "task": task,
            "stage": stage_name,
            "progress": progress,
            "status": "working" if progress < 100 else "complete",
            "timestamp": asyncio.get_event_loop().time()
        }
    
    yield {
        "type": "done",
        "skill": "progress",
        "task": task,
        "result": f"{task} completed successfully!",
        "final_progress": 100
    }


# =============================================================================
# Skill Registry for easy access
# =============================================================================

SKILL_REGISTRY = {
    "chat": chat_stream,
    "count": count_stream,
    "story": story_generator,
    "progress": progress_simulator,
}


def get_skill_generator(skill_name: str, params: Dict) -> Any:
    """
    Get the appropriate generator for a skill with given parameters.
    
    Args:
        skill_name: Name of the skill to execute
        params: Parameters for the skill
        
    Returns:
        Async generator or None if skill not found
    """
    if skill_name == "chat":
        return chat_stream(params.get("message", "Hello"))
    elif skill_name == "count":
        return count_stream(
            params.get("start", 1),
            params.get("end", 10),
            params.get("delay", 0.5)
        )
    elif skill_name == "story":
        return story_generator(params.get("theme", "adventure"))
    elif skill_name == "progress":
        return progress_simulator(params.get("task", "processing"))
    return None
