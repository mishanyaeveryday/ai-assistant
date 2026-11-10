"""Operating apps on screen: finding a point and acting on it.

Nothing here touches the real screen, mouse or keyboard, and no model is
asked: the capture, pyautogui and the vision model are all stand-ins. The
screen is a Retina one - captured at twice the size clicks work in.
"""
import asyncio
import base64
import io
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import openai
import pytest
from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from config.settings import TOOLS_REQUIRING_APPROVAL  # noqa: E402
from mcp_tools import permissions  # noqa: E402
from mcp_tools.input_control import server as input_server  # noqa: E402
from mcp_tools.screenshot_command import server as screen_server  # noqa: E402
from mcp_tools.screenshot_command.server import point_from_answer  # noqa: E402

SCREEN = (1512, 982)
CAPTURE = (3024, 1964)
# Deliberately lopsided, so a swapped x and y would land somewhere else:
# x is 600-800 of 1000, y is 100-200.
BOX = '{"box_2d": [100, 600, 200, 800]}'
POINT = (1058, 147)


# --- point_from_answer ---

@pytest.mark.parametrize("answer", [
    BOX,
    f"```json\n{BOX}\n```",
    f"Here it is: {BOX} - the button.",
    '[{"box_2d": [100, 600, 200, 800], "label": "Send"}]',
    "[100, 600, 200, 800]",
])
def test_point_is_the_box_centre_in_screen_points(answer):
    assert point_from_answer(answer, SCREEN) == POINT


def test_not_found_carries_the_models_reason():
    with pytest.raises(LookupError, match="only the desktop"):
        point_from_answer('{"found": false, "reason": "only the desktop"}', SCREEN)


@pytest.mark.parametrize("answer", [
    "I can't see it",
    '{"box_2d": [1, 2, 3]}',
    '{"box_2d": [100, 600, 200, 1200]}',
    '{"box_2d": [300, 600, 200, 800]}',
    '{"box_2d": ["a", 2, 3, 4]}',
    '{"box": [1, 2, 3, 4]}',
])
def test_unusable_answers_are_refused(answer):
    with pytest.raises(ValueError):
        point_from_answer(answer, SCREEN)


# --- find_on_screen ---

class FakeVision:
    """Stands in for the OpenRouter client; keeps the request it was sent."""

    def __init__(self, answer):
        self.answer = answer
        self.request = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **request):
        self.request = request
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.answer))])

    def sent_image(self) -> Image.Image:
        url = self.request["messages"][0]["content"][0]["image_url"]["url"]
        return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))


MODEL = "someone/vision-model-from-env"


def find(target, answer, screen_access=None, sees_images=True):
    vision = answer if isinstance(answer, FakeVision) else FakeVision(answer)
    with patch.object(screen_server.ImageGrab, "grab", return_value=Image.new("RGB", CAPTURE)) as grab, \
            patch.object(screen_server.pyautogui, "size", return_value=SCREEN), \
            patch.object(screen_server, "missing_screen_access", return_value=screen_access), \
            patch.object(screen_server, "VISION_MODEL", MODEL), \
            patch.object(screen_server, "_sees_images", AsyncMock(return_value=sees_images)), \
            patch.object(screen_server, "_llm", return_value=vision):
        result = asyncio.run(screen_server.find_on_screen(target))
    vision.grabbed = grab.called
    return result, vision


def test_find_on_screen_answers_in_click_coordinates():
    result, vision = find("the Send button", BOX)

    assert result == "Found 'the Send button' at x=1058, y=147."
    # VISION_MODEL looks, whatever model answers in the chat.
    assert vision.request["model"] == MODEL
    assert "the Send button" in vision.request["messages"][0]["content"][1]["text"]
    # Scaled down to the size clicks work in before it is sent.
    assert vision.sent_image().size == SCREEN


def test_find_on_screen_reports_what_the_model_saw_instead():
    result, _ = find("the Send button", '{"found": false, "reason": "a login form"}')

    assert result == "Not found on screen: the Send button. a login form"


def test_find_on_screen_reports_an_unreadable_answer():
    result, _ = find("the Send button", "somewhere on the right")

    assert result.startswith("The model's answer could not be read as a position")


def test_find_on_screen_says_when_it_may_not_see_the_screen():
    result, vision = find("the Send button", BOX, screen_access="no Screen Recording")

    assert result == "no Screen Recording"
    assert not vision.grabbed
    assert vision.request is None


def test_a_model_without_vision_is_not_sent_the_screen_but_warns():
    result, vision = find("the Send button", BOX, sees_images=False)

    assert f"'{MODEL}' cannot see images" in result
    assert "VISION_MODEL in .env" in result
    assert vision.request is None


class RefusingVision(FakeVision):
    """A model OpenRouter does not list, which turns the image down."""

    async def _create(self, **request):
        import httpx2
        self.request = request
        response = httpx2.Response(404, request=httpx2.Request(
            "POST", "https://openrouter.ai/api/v1/chat/completions"))
        raise openai.NotFoundError("No endpoints found that support image input",
                                   response=response, body=None)


def test_a_refused_image_gives_the_same_warning():
    result, vision = find("the Send button", RefusingVision(BOX), sees_images=None)

    assert vision.request is not None
    assert f"'{MODEL}' cannot see images" in result


def test_whether_the_model_sees_images_is_asked_once():
    fetch = AsyncMock(return_value=[
        {"id": MODEL, "architecture": {"input_modalities": ["text"]}}])
    with patch.object(screen_server, "VISION_MODEL", MODEL), \
            patch.object(screen_server, "fetch_models", fetch), \
            patch.object(screen_server, "_sees_images_answer", None):
        assert asyncio.run(screen_server._sees_images()) is False
        assert asyncio.run(screen_server._sees_images()) is False
    assert fetch.await_count == 1


def test_no_connection_leaves_it_open_and_asks_again():
    fetch = AsyncMock(side_effect=OSError("offline"))
    with patch.object(screen_server, "fetch_models", fetch), \
            patch.object(screen_server, "_sees_images_answer", None):
        assert asyncio.run(screen_server._sees_images()) is None
        assert asyncio.run(screen_server._sees_images()) is None
    assert fetch.await_count == 2


# --- input tools ---

@pytest.fixture
def screen():
    """pyautogui with its actions recorded instead of performed."""
    with patch.object(input_server.pyautogui, "size", return_value=SCREEN), \
            patch.object(input_server, "_stopped_by_user", False), \
            patch.object(input_server, "missing_input_access", return_value=None) as access, \
            patch.object(input_server.pyautogui, "click") as click, \
            patch.object(input_server.pyautogui, "hotkey") as hotkey, \
            patch.object(input_server.pyautogui, "scroll") as scroll, \
            patch.object(input_server.pyperclip, "copy") as copy:
        yield SimpleNamespace(click=click, hotkey=hotkey, scroll=scroll, copy=copy, access=access)


def test_click_inside_the_screen(screen):
    result = asyncio.run(input_server.click(*POINT))

    screen.click.assert_called_once_with(x=1058, y=147, clicks=1, button="left")
    assert result.startswith("Clicked at (1058, 147)")


def test_click_off_screen_is_refused_instead_of_clamped(screen):
    # Where the point lands if it is read off the full-size capture.
    result = asyncio.run(input_server.click(2116, 294))

    screen.click.assert_not_called()
    assert "outside the screen, which is 1512x982" in result


def test_type_text_clicks_the_field_first(screen):
    calls = []
    screen.click.side_effect = lambda **kw: calls.append("click")
    screen.copy.side_effect = lambda text: calls.append("copy")
    screen.hotkey.side_effect = lambda *keys: calls.append("paste")

    asyncio.run(input_server.type_text("привет", x=100, y=200))

    assert calls == ["click", "copy", "paste"]
    screen.click.assert_called_once_with(x=100, y=200)
    screen.copy.assert_called_once_with("привет")


def test_type_text_needs_both_coordinates(screen):
    result = asyncio.run(input_server.type_text("hi", x=100))

    assert result == "Give both x and y, or neither."
    screen.copy.assert_not_called()


def test_press_keys_maps_the_names_models_use(screen):
    result = asyncio.run(input_server.press_keys("Cmd+Shift+T"))

    screen.hotkey.assert_called_once_with("command", "shift", "t", interval=0.05)
    assert result == "Pressed command+shift+t"


def test_press_keys_repeats_and_focuses_first(screen):
    asyncio.run(input_server.press_keys("down", times=3, x=10, y=20))

    screen.click.assert_called_once_with(x=10, y=20)
    assert screen.hotkey.call_args_list == [call("down", interval=0.05)] * 3


def test_press_keys_refuses_unknown_keys(screen):
    result = asyncio.run(input_server.press_keys("hyper+x"))

    screen.hotkey.assert_not_called()
    assert result.startswith("Unknown key(s): 'hyper'")


def test_scroll_down_at_a_point(screen):
    result = asyncio.run(input_server.scroll("down", amount=3, x=500, y=400))

    screen.scroll.assert_called_once_with(-3, x=500, y=400)
    assert result == "Scrolled down by 3 at (500, 400)"


def test_scroll_refuses_a_bad_direction(screen):
    assert asyncio.run(input_server.scroll("left")) == "direction must be 'up' or 'down'."
    screen.scroll.assert_not_called()


@pytest.mark.parametrize("act", [
    lambda: input_server.click(*POINT),
    lambda: input_server.type_text("hi", x=100, y=200),
    lambda: input_server.press_keys("enter"),
    lambda: input_server.scroll("down"),
])
def test_without_accessibility_nothing_is_sent(screen, act):
    # macOS would drop the events without a word; the tool says so instead.
    screen.access.return_value = "no Accessibility"

    assert asyncio.run(act()) == "no Accessibility"
    for action in (screen.click, screen.hotkey, screen.scroll, screen.copy):
        action.assert_not_called()


# --- macOS permissions ---

def test_missing_permissions_are_named_on_a_mac():
    with patch.object(permissions, "IS_MAC", True), \
            patch.object(permissions, "_allowed", return_value=False):
        assert "Accessibility" in permissions.missing_input_access()
        assert "Screen Recording" in permissions.missing_screen_access()


def test_permissions_are_not_checked_elsewhere():
    with patch.object(permissions, "IS_MAC", False), \
            patch.object(permissions, "_allowed", return_value=False):
        assert permissions.missing_input_access() is None
        assert permissions.missing_screen_access() is None


def test_acting_tools_ask_before_running():
    assert {"click", "type_text", "press_keys", "scroll"} <= TOOLS_REQUIRING_APPROVAL
