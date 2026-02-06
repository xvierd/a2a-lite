"""
Tests for the Agent class.
"""
import pytest
from a2a_lite import Agent


def test_agent_creation():
    """Test basic agent creation."""
    agent = Agent(name="Test", description="Test agent")
    assert agent.name == "Test"
    assert agent.description == "Test agent"
    assert agent.version == "1.0.0"


def test_agent_with_custom_version():
    """Test agent with custom version."""
    agent = Agent(name="Test", description="Test", version="2.5.0")
    assert agent.version == "2.5.0"


def test_skill_registration():
    """Test that skills are properly registered."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("greet")
    async def greet(name: str) -> str:
        return f"Hello, {name}"

    assert "greet" in agent._skills
    assert agent._skills["greet"].name == "greet"
    assert agent._skills["greet"].is_async is True


def test_skill_with_custom_name():
    """Test skill registration with custom name."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("custom_name", description="Custom description")
    async def my_func(x: int) -> int:
        return x * 2

    assert "custom_name" in agent._skills
    assert "my_func" not in agent._skills
    assert agent._skills["custom_name"].description == "Custom description"


def test_skill_input_schema_extraction():
    """Test that input schemas are extracted from type hints."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("add")
    async def add(a: int, b: int) -> int:
        return a + b

    skill = agent._skills["add"]
    assert skill.input_schema["properties"]["a"]["type"] == "integer"
    assert skill.input_schema["properties"]["b"]["type"] == "integer"
    assert "a" in skill.input_schema["required"]
    assert "b" in skill.input_schema["required"]


def test_skill_with_default_params():
    """Test schema extraction with default parameters."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("greet")
    async def greet(name: str = "World") -> str:
        return f"Hello, {name}"

    skill = agent._skills["greet"]
    assert "name" in skill.input_schema["properties"]
    assert "name" not in skill.input_schema["required"]  # Has default


def test_skill_output_schema():
    """Test output schema extraction."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("get_data")
    async def get_data() -> dict:
        return {"key": "value"}

    skill = agent._skills["get_data"]
    assert skill.output_schema["type"] == "object"


def test_multiple_skills():
    """Test registering multiple skills."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("skill1")
    async def skill1() -> str:
        return "one"

    @agent.skill("skill2")
    async def skill2() -> str:
        return "two"

    @agent.skill("skill3")
    async def skill3() -> str:
        return "three"

    assert len(agent._skills) == 3
    assert "skill1" in agent._skills
    assert "skill2" in agent._skills
    assert "skill3" in agent._skills


def test_agent_card_generation():
    """Test Agent Card generation."""
    agent = Agent(name="Test", description="A test agent", version="2.0.0")

    @agent.skill("greet", description="Greet someone")
    async def greet(name: str) -> str:
        return f"Hello, {name}"

    card = agent.build_agent_card("localhost", 8787)

    assert card.name == "Test"
    assert card.description == "A test agent"
    assert card.version == "2.0.0"
    assert len(card.skills) == 1
    assert card.skills[0].name == "greet"
    assert card.skills[0].description == "Greet someone"


def test_agent_card_url():
    """Test Agent Card URL generation."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("test")
    async def test_skill() -> str:
        return "test"

    card = agent.build_agent_card("example.com", 9000)
    assert card.url == "http://example.com:9000"


def test_agent_card_custom_url():
    """Test Agent Card with custom URL."""
    agent = Agent(name="Test", description="Test", url="https://my-agent.example.com")

    @agent.skill("test")
    async def test_skill() -> str:
        return "test"

    card = agent.build_agent_card()
    assert card.url == "https://my-agent.example.com"


def test_error_handler_registration():
    """Test error handler registration."""
    agent = Agent(name="Test", description="Test")

    @agent.on_error
    async def handle_error(error):
        return {"error": str(error)}

    assert agent._error_handler is not None


def test_startup_hook_registration():
    """Test startup hook registration."""
    agent = Agent(name="Test", description="Test")

    @agent.on_startup
    async def startup():
        pass

    assert len(agent._on_startup) == 1


def test_shutdown_hook_registration():
    """Test shutdown hook registration."""
    agent = Agent(name="Test", description="Test")

    @agent.on_shutdown
    async def shutdown():
        pass

    assert len(agent._on_shutdown) == 1


def test_sync_skill():
    """Test that sync skills are also supported."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("sync_skill")
    def sync_skill(x: int) -> int:
        return x * 2

    skill = agent._skills["sync_skill"]
    assert skill.is_async is False


def test_skill_with_tags():
    """Test skill with tags."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("tagged", tags=["math", "calculation"])
    async def tagged(a: int, b: int) -> int:
        return a + b

    skill = agent._skills["tagged"]
    assert skill.tags == ["math", "calculation"]


def test_streaming_skill_registration():
    """Test that streaming skills are properly detected."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("stream", streaming=True)
    async def stream_skill(msg: str):
        for word in msg.split():
            yield word

    skill = agent._skills["stream"]
    assert skill.is_streaming is True
    assert agent._has_streaming is True


def test_streaming_auto_detection():
    """Test auto-detection of generator functions as streaming."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("auto_stream")
    async def gen_skill(msg: str):
        yield "hello"
        yield "world"

    skill = agent._skills["auto_stream"]
    assert skill.is_streaming is True


def test_add_middleware():
    """Test non-decorator middleware registration."""
    agent = Agent(name="Test", description="Test")

    async def my_middleware(ctx, next):
        return await next()

    agent.add_middleware(my_middleware)
    assert len(agent._middleware._middlewares) == 1


def test_middleware_decorator():
    """Test middleware decorator registration."""
    agent = Agent(name="Test", description="Test")

    @agent.middleware
    async def my_middleware(ctx, next):
        return await next()

    assert len(agent._middleware._middlewares) == 1


def test_on_complete_registration():
    """Test completion hook registration."""
    agent = Agent(name="Test", description="Test")

    @agent.on_complete
    async def complete(skill, result, ctx):
        pass

    assert len(agent._on_complete) == 1


def test_multiple_startup_hooks():
    """Test registering multiple startup hooks."""
    agent = Agent(name="Test", description="Test")

    @agent.on_startup
    async def hook1():
        pass

    @agent.on_startup
    async def hook2():
        pass

    assert len(agent._on_startup) == 2


def test_task_store_memory():
    """Test agent with memory task store."""
    from a2a_lite.tasks import TaskStore

    agent = Agent(name="Test", description="Test", task_store="memory")
    assert isinstance(agent._task_store, TaskStore)


def test_task_store_custom():
    """Test agent with custom task store."""
    from a2a_lite.tasks import TaskStore

    custom_store = TaskStore()
    agent = Agent(name="Test", description="Test", task_store=custom_store)
    assert agent._task_store is custom_store


def test_task_store_none():
    """Test agent with no task store (default)."""
    agent = Agent(name="Test", description="Test")
    assert agent._task_store is None


def test_auth_default_noauth():
    """Test that default auth is NoAuth."""
    from a2a_lite.auth import NoAuth

    agent = Agent(name="Test", description="Test")
    assert isinstance(agent._auth, NoAuth)


def test_auth_custom():
    """Test agent with custom auth."""
    from a2a_lite.auth import APIKeyAuth

    auth = APIKeyAuth(keys=["test-key"])
    agent = Agent(name="Test", description="Test", auth=auth)
    assert agent._auth is auth


def test_agent_card_streaming_capability():
    """Test that agent card reflects streaming capability."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("stream", streaming=True)
    async def stream_skill(msg: str):
        yield msg

    card = agent.build_agent_card()
    assert card.capabilities.streaming is True


def test_agent_card_no_streaming():
    """Test that agent card correctly reports no streaming."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("simple")
    async def simple() -> str:
        return "ok"

    card = agent.build_agent_card()
    assert card.capabilities.streaming is False


def test_agent_card_push_notifications():
    """Test agent card push notifications capability."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("test")
    async def test_skill() -> str:
        return "ok"

    @agent.on_complete
    async def on_complete(skill, result, ctx):
        pass

    card = agent.build_agent_card()
    assert card.capabilities.push_notifications is True


def test_skill_name_from_function():
    """Test that skill name defaults to function name when None."""
    agent = Agent(name="Test", description="Test")

    @agent.skill()
    async def my_skill(x: int) -> int:
        return x

    assert "my_skill" in agent._skills


def test_skill_description_from_docstring():
    """Test that skill description falls back to docstring."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("doc_skill")
    async def doc_skill(x: int) -> int:
        """This is the docstring description."""
        return x

    skill = agent._skills["doc_skill"]
    assert "docstring description" in skill.description


def test_get_app_returns_starlette():
    """Test that get_app returns a working Starlette app."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("test")
    async def test_skill() -> str:
        return "ok"

    app = agent.get_app()
    assert app is not None
    assert hasattr(app, "routes")


def test_get_app_with_cors():
    """Test that get_app includes CORS middleware when configured."""
    agent = Agent(name="Test", description="Test", cors_origins=["http://localhost:3000"])

    @agent.skill("test")
    async def test_skill() -> str:
        return "ok"

    app = agent.get_app()
    assert app is not None


def test_skill_with_task_context_detection():
    """Test that skills needing TaskContext are detected."""
    from a2a_lite.tasks import TaskContext

    agent = Agent(name="Test", description="Test", task_store="memory")

    @agent.skill("process")
    async def process(data: str, task: TaskContext) -> str:
        return data

    skill = agent._skills["process"]
    assert skill.needs_task_context is True
    assert skill.task_context_param == "task"


def test_skill_with_auth_detection():
    """Test that skills needing AuthResult are detected."""
    from a2a_lite.auth import AuthResult

    agent = Agent(name="Test", description="Test")

    @agent.skill("whoami")
    async def whoami(auth: AuthResult) -> str:
        return "ok"

    skill = agent._skills["whoami"]
    assert skill.needs_auth is True
    assert skill.auth_param == "auth"


def test_production_flag():
    """Test production flag is set."""
    agent = Agent(name="Test", description="Test", production=True)
    assert agent.production is True
