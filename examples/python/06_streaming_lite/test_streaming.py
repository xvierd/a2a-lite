"""
Unit tests for Streaming Agent.

Demonstrates testing streaming skills with AgentTestClient.
"""

import pytest
from agent import agent
from a2a_lite import AgentTestClient


def test_chat_streaming():
    """Test chat skill returns multiple chunks."""
    client = AgentTestClient(agent)
    
    chunks = client.stream("chat", message="Hello")
    
    # Should get multiple tokens
    assert len(chunks) > 1
    
    # Each chunk should have a token
    for chunk in chunks[:-1]:  # All except possibly last
        assert "token" in chunk


def test_count_streaming():
    """Test count skill streams numbers."""
    client = AgentTestClient(agent)
    
    chunks = client.stream("count", start=1, end=5)
    
    # Should get 5 number chunks
    numbers = [c["number"] for c in chunks if "number" in c]
    assert numbers == [1, 2, 3, 4, 5]


def test_count_progress():
    """Test count skill includes progress info."""
    client = AgentTestClient(agent)
    
    chunks = client.stream("count", start=1, end=4)
    
    # Check progress in chunks
    progress_chunks = [c for c in chunks if "progress" in c]
    assert len(progress_chunks) == 4
    
    # First should be 25%, last should be 100%
    assert progress_chunks[0]["progress"]["percentage"] == 25.0
    assert progress_chunks[-1]["progress"]["percentage"] == 100.0


def test_story_streaming():
    """Test story skill streams parts."""
    client = AgentTestClient(agent)
    
    chunks = client.stream("story", theme="adventure")
    
    # Should get story parts
    parts = [c for c in chunks if "part" in c]
    assert len(parts) > 0
    
    # Parts should be sequential
    for i, chunk in enumerate(parts):
        assert chunk["part_number"] == i + 1


def test_progress_simulation():
    """Test progress skill."""
    client = AgentTestClient(agent)
    
    chunks = client.stream("progress", task="upload")
    
    # Should get progress updates
    progress_values = [c["progress"] for c in chunks if "progress" in c]
    assert len(progress_values) > 0
    assert progress_values[-1] == 100  # Completes at 100%


def test_non_streaming_call():
    """Test non-streaming call returns collected results."""
    client = AgentTestClient(agent)
    
    # Call without streaming collects all chunks
    result = client.call("chat", message="Hi")
    
    # Returns the last chunk or collected data
    assert result is not None


if __name__ == "__main__":
    print("Running streaming tests...")
    
    client = AgentTestClient(agent)
    
    # Test chat
    print("\n1. Testing chat streaming...")
    chunks = client.stream("chat", message="Hello world")
    print(f"   Received {len(chunks)} chunks")
    print(f"   First token: '{chunks[0].get('token', 'N/A')}'")
    
    # Test count
    print("\n2. Testing count streaming...")
    chunks = client.stream("count", start=1, end=5)
    numbers = [c["number"] for c in chunks if "number" in c]
    print(f"   Numbers: {numbers}")
    
    # Test story
    print("\n3. Testing story streaming...")
    chunks = client.stream("story", theme="mystery")
    parts = [c["part"] for c in chunks if "part" in c]
    print(f"   Generated story with {len(parts)} parts")
    print(f"   First part: '{parts[0][:50]}...'")
    
    print("\n✅ All streaming tests completed!")
