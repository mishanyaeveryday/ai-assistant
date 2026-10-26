"""Settings > Model: the model and OpenRouter key each user's prompts go
out with, falling back to the ones in .env."""
import asyncio
import os
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from cryptography.fernet import Fernet
from PySide6.QtCore import QObject, Signal

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from agent.mcp_registry import MCPRegistry  # noqa: E402
from core import services  # noqa: E402
from core.crypto import SecretBox  # noqa: E402
from core.openrouter import accepts_images, fetch_models, fetch_tool_models  # noqa: E402
from core.services import MCPServerService, ModelSettingsService, SecretService  # noqa: E402
from db.database import MCPServer_DB, Secret_DB, User_DB  # noqa: E402
from interface.gui import controller as controller_module  # noqa: E402
from interface.gui.controller import ModelSettingsController  # noqa: E402
from tests.unit import test_chat_tasks  # noqa: E402

DEFAULT_MODEL = "qwen/qwen3.8-flash"
ENV_KEY = "sk-or-v1-from-env"
OWN_KEY = "sk-or-v1-my-own-key"
TOOL_MODELS = ["anthropic/claude-sonnet-5.5", "openai/gpt-5-mini", DEFAULT_MODEL]


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.sqlite3")


@pytest.fixture
def users(db_path):
    db = User_DB(db_name=db_path)
    db.create_table()
    return db


@pytest.fixture
def service(db_path, users, monkeypatch):
    secret_db = Secret_DB(db_name=db_path)
    secret_db.create_table()
    secrets = SecretService(secret_db=secret_db, secret_box=SecretBox(key=Fernet.generate_key()))
    # As if .env had these.
    monkeypatch.setattr(services, "LLM_MODEL", DEFAULT_MODEL)
    monkeypatch.setattr(services, "OPENROUTER_API_KEY", ENV_KEY)
    return ModelSettingsService(user_db=users, secret_service=secrets)


@pytest.fixture
def alice(users):
    return users.add_user("alice", "alice@example.com", "hash")


@pytest.fixture
def bob(users):
    return users.add_user("bob", "bob@example.com", "hash")


# --- ModelSettingsService ---

def test_without_settings_the_env_key_and_default_model_are_used(service, alice):
    assert service.llm_config(alice) == (DEFAULT_MODEL, ENV_KEY)
    assert service.key_source(alice) == service.KEY_FROM_ENV


def test_own_key_and_model_win_over_env(service, alice):
    service.set_model(alice, "openai/gpt-5-mini")
    service.set_api_key(alice, f"  {OWN_KEY}\n")

    assert service.llm_config(alice) == ("openai/gpt-5-mini", OWN_KEY)
    assert service.key_source(alice) == service.KEY_FROM_USER


def test_own_key_is_stored_encrypted(service, alice, db_path):
    service.set_api_key(alice, OWN_KEY)

    with open(db_path, "rb") as f:
        assert OWN_KEY.encode() not in f.read()


def test_removing_the_key_goes_back_to_env(service, alice, monkeypatch):
    service.set_api_key(alice, OWN_KEY)

    assert service.remove_api_key(alice)
    assert service.llm_config(alice) == (DEFAULT_MODEL, ENV_KEY)

    monkeypatch.setattr(services, "OPENROUTER_API_KEY", None)
    assert service.llm_config(alice) == (DEFAULT_MODEL, None)
    assert service.key_source(alice) is None


def test_picking_the_default_keeps_following_env(service, alice, users, monkeypatch):
    service.set_model(alice, "openai/gpt-5-mini")
    service.set_model(alice, DEFAULT_MODEL)

    assert users.get_llm_model(alice) is None
    monkeypatch.setattr(services, "LLM_MODEL", "google/gemini-3.8-flash")
    assert service.get_model(alice) == "google/gemini-3.8-flash"


def test_one_users_settings_are_not_anothers(service, alice, bob):
    service.set_model(alice, "openai/gpt-5-mini")
    service.set_api_key(alice, OWN_KEY)

    assert service.llm_config(bob) == (DEFAULT_MODEL, ENV_KEY)
    assert service.key_source(bob) == service.KEY_FROM_ENV


def test_users_table_from_before_gets_the_column(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, "
                     "email TEXT UNIQUE NOT NULL, password TEXT NOT NULL)")
        conn.execute("INSERT INTO users VALUES ('old', 'old', 'old@example.com', 'hash')")

    users = User_DB(db_name=db_path)
    users.create_table()

    assert users.get_llm_model("old") is None
    assert users.set_llm_model("old", "openai/gpt-5-mini")
    assert users.get_user_by_id("old")["llm_model"] == "openai/gpt-5-mini"


# --- The model and key reach the request ---

class FakeLLM:
    def __init__(self, llm_model, api_key, base_url, fallback_models=()):
        self.llm_model = llm_model
        self.api_key = api_key


def test_ai_client_uses_the_model_and_key_it_is_given():
    from agent import orchestrator

    with patch.object(orchestrator, "LLMClient", FakeLLM):
        client = orchestrator.AIClient(memory=[], mcp_registry=None,
                                       model="openai/gpt-5-mini", api_key=OWN_KEY)
        fallback = orchestrator.AIClient(memory=[], mcp_registry=None)

    assert (client.llm.llm_model, client.llm.api_key) == ("openai/gpt-5-mini", OWN_KEY)
    assert (fallback.llm.llm_model, fallback.llm.api_key) == (
        orchestrator.LLM_MODEL, orchestrator.OPENROUTER_API_KEY)


def test_each_prompt_takes_the_logged_in_users_settings(service, alice):
    async def scenario():
        controller, view = test_chat_tasks.make_controller(model_settings=service)
        controller.set_user(alice)
        view.open_chat("A")

        async def prompt(text, change_settings=lambda: None):
            view.send_input.emit("A", text)
            await test_chat_tasks.settle()
            change_settings()
            # Each prompt waits on an approval card; answering it ends it.
            view.cards[-1][1].click(True)
            await test_chat_tasks.settle()

        def change_settings():
            service.set_model(alice, "openai/gpt-5-mini")
            service.set_api_key(alice, OWN_KEY)

        # Changed in settings while a task runs: counts from the next prompt.
        await prompt("first", change_settings)
        await prompt("second")
        view.logout_requested.emit()
        await prompt("after logout")

    test_chat_tasks.run(scenario)

    sent = [(w.llm_model, w.api_key) for w in test_chat_tasks.FakeWorker.instances]
    assert sent == [(DEFAULT_MODEL, ENV_KEY), ("openai/gpt-5-mini", OWN_KEY), (None, None)]


# --- OpenRouter's model list ---

def test_only_models_that_can_use_tools_are_listed():
    def handler(request):
        assert request.url == "https://openrouter.ai/api/v1/models"
        return httpx.Response(200, json={"data": [
            {"id": "openai/gpt-5-mini", "supported_parameters": ["tools", "temperature"]},
            {"id": "some/text-only", "supported_parameters": ["temperature"]},
            {"id": "anthropic/claude-sonnet-5.5", "supported_parameters": ["tool_choice", "tools"]},
            {"id": "no/params"},
        ]})

    models = asyncio.run(fetch_tool_models(transport=httpx.MockTransport(handler)))

    assert models == ["anthropic/claude-sonnet-5.5", "openai/gpt-5-mini"]


def test_which_models_see_images():
    def handler(request):
        return httpx.Response(200, json={"data": [
            {"id": DEFAULT_MODEL, "architecture": {"input_modalities": ["text", "image"]}},
            {"id": "deepseek/deepseek-v4-flash", "architecture": {"input_modalities": ["text"]}},
        ]})

    models = asyncio.run(fetch_models(transport=httpx.MockTransport(handler)))

    assert accepts_images(models, DEFAULT_MODEL) is True
    assert accepts_images(models, "deepseek/deepseek-v4-flash") is False
    assert accepts_images(models, "not/listed") is None


# --- The server that looks at images gets the same key and model ---

class FakeClient:
    """Stands in for MCPClient; keeps what each server would be started with."""

    def __init__(self):
        self.specs = {}
        self.disconnected = []

    async def call_tool(self, spec, tool_name, arguments):
        self.specs[spec.name] = spec

    async def disconnect(self, server_id):
        self.disconnected.append(server_id)
        return True


def make_registry(service, user_id, db_path):
    mcp_db = MCPServer_DB(db_name=db_path)
    mcp_db.create_table()
    servers = MCPServerService(mcp_server_db=mcp_db, secret_service=service.secret_service)
    servers.ensure_builtin_servers(user_id)
    for server in servers.get_user_servers(user_id):
        servers.update_server(server.id, last_status='ok', known_tools=[
            {'name': f'{server.name}_tool', 'inputSchema': {}}])
    servers.set_screen_control_allowed(user_id, True)
    client = FakeClient()
    registry = MCPRegistry(servers, client, user_id=user_id, model_settings=service)
    return registry, client, servers


def start(registry, *tools):
    async def calls():
        for tool in tools:
            await registry.call_tool(tool, {})
    asyncio.run(calls())


def test_screen_server_is_started_with_the_users_key_and_model(service, alice, db_path):
    service.set_model(alice, "openai/gpt-5-mini")
    service.set_api_key(alice, OWN_KEY)
    registry, client, _ = make_registry(service, alice, db_path)

    start(registry, "screenshot_command_tool", "terminal_command_tool")

    assert client.specs["screenshot_command"].env == {
        "LLM_MODEL": "openai/gpt-5-mini", "OPENROUTER_API_KEY": OWN_KEY}
    # A server running shell commands would hand it to every command.
    assert "OPENROUTER_API_KEY" not in (client.specs["terminal_command"].env or {})


def test_screen_server_gets_the_env_key_or_none(service, alice, db_path, monkeypatch):
    registry, client, _ = make_registry(service, alice, db_path)

    start(registry, "screenshot_command_tool")
    assert client.specs["screenshot_command"].env == {
        "LLM_MODEL": DEFAULT_MODEL, "OPENROUTER_API_KEY": ENV_KEY}

    monkeypatch.setattr(services, "OPENROUTER_API_KEY", None)
    start(registry, "screenshot_command_tool")
    assert client.specs["screenshot_command"].env == {"LLM_MODEL": DEFAULT_MODEL}


def test_stopping_openrouter_servers_leaves_the_rest_running(service, alice, db_path):
    registry, client, servers = make_registry(service, alice, db_path)

    asyncio.run(registry.stop_openrouter_servers(alice))

    assert client.disconnected == [servers.get_server_by_name(alice, "screenshot_command").id]


# --- ModelSettingsController ---

class FakeModelView(QObject):
    save_requested = Signal(str, str)
    remove_key_requested = Signal()
    opened = Signal()

    def __init__(self):
        super().__init__()
        self.settings = None
        self.models = None
        self.unavailable = False
        self.error = None
        self.saved = False

    def show_settings(self, model, default_model, key_source):
        self.settings = {"model": model, "default_model": default_model,
                         "key_source": key_source}
        self.error = None

    def show_models(self, models):
        self.models = models

    def show_models_unavailable(self):
        self.unavailable = True

    def show_error(self, text):
        self.error = text

    def show_saved(self):
        self.saved = True


async def listed_models():
    return list(TOOL_MODELS)


async def no_connection():
    raise httpx.ConnectError("offline")


class FakeRegistry:
    def __init__(self):
        self.restarted = []

    async def stop_openrouter_servers(self, user_id):
        self.restarted.append(user_id)


def make_model_controller(service, user_id, fetch_models=listed_models, registry=None):
    view = FakeModelView()
    user = SimpleNamespace(id=user_id, username="alice")
    controller = ModelSettingsController(user=user, model=service, view=view,
                                         mcp_registry=registry, fetch_models=fetch_models)
    return controller, view


def test_opening_shows_what_is_in_use_and_loads_the_list(service, alice):
    async def scenario():
        controller, view = make_model_controller(service, alice)
        view.opened.emit()
        await test_chat_tasks.settle()
        return view

    view = asyncio.run(scenario())

    assert view.settings == {"model": DEFAULT_MODEL, "default_model": DEFAULT_MODEL,
                             "key_source": "env"}
    assert view.models == TOOL_MODELS


def test_saving_a_model_and_key(service, alice):
    async def scenario():
        controller, view = make_model_controller(service, alice)
        view.opened.emit()
        await test_chat_tasks.settle()
        view.save_requested.emit(" openai/gpt-5-mini ", OWN_KEY)
        return view

    view = asyncio.run(scenario())

    assert view.saved and view.error is None
    assert service.llm_config(alice) == ("openai/gpt-5-mini", OWN_KEY)
    # The key is never handed back to the view, only where it comes from.
    assert view.settings == {"model": "openai/gpt-5-mini", "default_model": DEFAULT_MODEL,
                             "key_source": "user"}


def test_empty_key_keeps_the_saved_one(service, alice):
    service.set_api_key(alice, OWN_KEY)

    async def scenario():
        controller, view = make_model_controller(service, alice)
        view.save_requested.emit("openai/gpt-5-mini", "")

    asyncio.run(scenario())

    assert service.llm_config(alice) == ("openai/gpt-5-mini", OWN_KEY)


@pytest.mark.parametrize("model, key, message", [
    ("", "", "Pick a model."),
    ("gpt-5-mini", "", "is not an OpenRouter model id"),
    ("openai/gpt 5", "", "is not an OpenRouter model id"),
    ("openai/no-such-model", "", "has no model"),
    ("openai/gpt-5-mini", "sk-or-v1 broken", "cannot contain spaces"),
])
def test_bad_input_is_refused(service, alice, model, key, message):
    async def scenario():
        controller, view = make_model_controller(service, alice)
        view.opened.emit()
        await test_chat_tasks.settle()
        view.save_requested.emit(model, key)
        return view

    view = asyncio.run(scenario())

    assert message in view.error
    assert not view.saved
    assert service.llm_config(alice) == (DEFAULT_MODEL, ENV_KEY)


def test_without_the_list_any_model_id_is_taken(service, alice):
    async def scenario():
        controller, view = make_model_controller(service, alice, fetch_models=no_connection)
        view.opened.emit()
        await test_chat_tasks.settle()
        view.save_requested.emit("someone/brand-new-model", "")
        return view

    view = asyncio.run(scenario())

    assert view.unavailable and view.models is None
    assert view.error is None
    assert service.get_model(alice) == "someone/brand-new-model"


def test_model_in_use_can_be_kept_even_if_no_longer_listed(service, alice):
    service.set_model(alice, "old/retired-model")

    async def scenario():
        controller, view = make_model_controller(service, alice)
        view.opened.emit()
        await test_chat_tasks.settle()
        view.save_requested.emit("old/retired-model", OWN_KEY)
        return view

    view = asyncio.run(scenario())

    assert view.error is None
    assert service.llm_config(alice) == ("old/retired-model", OWN_KEY)


def test_remove_key(service, alice):
    service.set_api_key(alice, OWN_KEY)

    async def scenario():
        controller, view = make_model_controller(service, alice)
        view.remove_key_requested.emit()
        return view

    view = asyncio.run(scenario())

    assert view.settings["key_source"] == "env"
    assert service.llm_config(alice) == (DEFAULT_MODEL, ENV_KEY)


@pytest.mark.parametrize("model, key, restarted", [
    ("openai/gpt-5-mini", "", True),
    (DEFAULT_MODEL, OWN_KEY, True),
    # Nothing changed: a screen task running now keeps its server.
    (DEFAULT_MODEL, "", False),
])
def test_screen_server_restarts_only_when_key_or_model_changes(service, alice, model, key,
                                                               restarted):
    registry = FakeRegistry()

    async def scenario():
        controller, view = make_model_controller(service, alice, registry=registry)
        view.save_requested.emit(model, key)
        await test_chat_tasks.settle()

    asyncio.run(scenario())

    assert registry.restarted == ([alice] if restarted else [])


def test_removing_the_key_restarts_the_screen_server(service, alice):
    service.set_api_key(alice, OWN_KEY)
    registry = FakeRegistry()

    async def scenario():
        controller, view = make_model_controller(service, alice, registry=registry)
        view.remove_key_requested.emit()
        await test_chat_tasks.settle()

    asyncio.run(scenario())

    assert registry.restarted == [alice]


def test_disconnected_controller_ignores_the_view(service, alice):
    async def scenario():
        controller, view = make_model_controller(service, alice)
        controller.disconnect_view()
        view.save_requested.emit("openai/gpt-5-mini", OWN_KEY)
        view.opened.emit()
        return view

    view = asyncio.run(scenario())

    assert view.settings is None
    assert service.llm_config(alice) == (DEFAULT_MODEL, ENV_KEY)