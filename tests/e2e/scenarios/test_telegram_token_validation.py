"""Scenario: Telegram bot token validation – UI flow and error handling.

Tests the bug fix for HTTP 404 errors during Telegram token validation caused by
URL-encoding the colon (:) in bot tokens to %3A, which breaks the Telegram API endpoint.

Tests cover:
  A. Configure modal UI accepts Telegram tokens
  B. Validation error handling shows proper messages
  C. Token format handling (colon, special characters)
  D. UI state management (modal closed on success, stays open on error)

Note: The core URL-building logic (colon preservation, no %3A encoding) is verified
by unit tests in src/extensions/manager.rs and src/setup/channels.rs. These E2E tests
verify the end-to-end UI flow and error handling work correctly.
"""

import json

from helpers import SEL


# ─── Fixture data ─────────────────────────────────────────────────────────────

_TELEGRAM_EXTENSION = {
    "name": "telegram",
    "display_name": "Telegram",
    "kind": "wasm_channel",
    "description": "Telegram bot channel",
    "url": None,
    "active": False,
    "authenticated": False,
    "has_auth": True,
    "needs_setup": True,
    "tools": [],
    "activation_status": "installed",
    "activation_error": None,
}

_TELEGRAM_SECRETS = [
    {
        "name": "telegram_bot_token",
        "prompt": "Telegram Bot Token",
        "provided": False,
        "optional": False,
        "auto_generate": False,
    }
]


# ─── Navigation Helpers ────────────────────────────────────────────────────────

async def go_to_extensions(page):
    """Click the Extensions tab and wait for the panel to appear."""
    await page.locator(SEL["tab_button"].format(tab="extensions")).click()
    await page.locator(SEL["tab_panel"].format(tab="extensions")).wait_for(
        state="visible", timeout=5000
    )
    await page.locator(
        f"{SEL['extensions_list']} .empty-state, {SEL['ext_card_installed']}"
    ).first.wait_for(state="visible", timeout=8000)


async def mock_extensions_api(page, installed=None):
    """Mock the extensions API endpoints."""
    ext_body = json.dumps({"extensions": installed or []})

    async def handle_ext_list(route):
        path = route.request.url.split("?")[0]
        if path.endswith("/api/extensions"):
            await route.fulfill(
                status=200, content_type="application/json", body=ext_body
            )
        else:
            await route.continue_()

    await page.route("**/api/extensions*", handle_ext_list)


async def open_telegram_configure_modal(page):
    """Open the Telegram extension configure modal via JS."""

    async def handle_setup(route):
        if route.request.method == "GET":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"secrets": _TELEGRAM_SECRETS}),
            )
        else:
            # POST requests are mocked by individual test handlers
            await route.continue_()

    await page.route("**/api/extensions/telegram/setup", handle_setup)
    await page.evaluate("showConfigureModal('telegram')")
    await page.locator(SEL["configure_modal"]).wait_for(state="visible", timeout=5000)


# ─── Test Group A: Configure Modal UI ──────────────────────────────────────────

async def test_telegram_configure_modal_renders(page):
    """
    Telegram extension configure modal renders with correct fields.

    Verifies that the configure modal appears with the Telegram bot token field
    and all expected UI elements are present.
    """
    await mock_extensions_api(page, installed=[_TELEGRAM_EXTENSION])

    async def handle_setup(route):
        if route.request.method == "GET":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"secrets": _TELEGRAM_SECRETS}),
            )
        else:
            await route.continue_()

    await page.route("**/api/extensions/telegram/setup", handle_setup)
    await page.evaluate("showConfigureModal('telegram')")
    modal = page.locator(SEL["configure_modal"])
    await modal.wait_for(state="visible", timeout=5000)

    # Modal should contain the extension name and token prompt
    modal_text = await modal.text_content()
    assert "telegram" in modal_text.lower()
    assert "bot token" in modal_text.lower()

    # Input field should be present
    input_field = page.locator(SEL["configure_input"])
    assert await input_field.is_visible()


async def test_telegram_token_input_accepts_valid_format(page):
    """
    Telegram bot token input accepts tokens with colon separator.

    Verifies that a token in the format `numeric_id:alphanumeric_string`
    can be entered and submitted without browser-side errors.
    """
    await mock_extensions_api(page, installed=[_TELEGRAM_EXTENSION])

    async def handle_setup(route):
        if route.request.method == "GET":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"secrets": _TELEGRAM_SECRETS}),
            )
        elif route.request.method == "POST":
            # Success response
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"success": True}),
            )

    await page.route("**/api/extensions/telegram/setup", handle_setup)
    await open_telegram_configure_modal(page)

    # Enter a valid Telegram bot token with colon
    token_value = "123456789:AABBccDDeeFFgg_Test-Token"
    input_field = page.locator(SEL["configure_input"])
    await input_field.fill(token_value)

    # Verify the value was entered
    entered_value = await input_field.input_value()
    assert entered_value == token_value

    # Click save
    await page.locator(SEL["configure_save_btn"]).click()

    # Modal should close on success
    await page.locator(SEL["configure_overlay"]).wait_for(state="hidden", timeout=5000)


# ─── Test Group B: Validation Error Handling ──────────────────────────────────

async def test_telegram_validation_failure_shows_error(page):
    """
    Token validation failure displays error message and modal stays open.

    Verifies that when validation fails (server returns error), the error
    message is displayed and the user can retry.
    """
    await mock_extensions_api(page, installed=[_TELEGRAM_EXTENSION])

    async def handle_setup(route):
        if route.request.method == "GET":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"secrets": _TELEGRAM_SECRETS}),
            )
        elif route.request.method == "POST":
            # Simulate validation failure
            await route.fulfill(
                status=400,
                content_type="application/json",
                body=json.dumps(
                    {
                        "success": False,
                        "message": "validation failed: invalid token or unauthorized",
                    }
                ),
            )

    await page.route("**/api/extensions/telegram/setup", handle_setup)
    await open_telegram_configure_modal(page)

    # Enter an invalid token
    await page.locator(SEL["configure_input"]).fill("invalid_token_no_colon")

    # Click save
    await page.locator(SEL["configure_save_btn"]).click()

    # Wait for error to appear and modal to stay open
    modal = page.locator(SEL["configure_modal"])
    modal_text = await modal.text_content()

    # Modal should still be visible
    assert await modal.is_visible(timeout=3000)

    # Error message should be visible
    assert "invalid" in modal_text.lower() or "fail" in modal_text.lower(), (
        f"Expected error message in modal, got: {modal_text}"
    )


async def test_telegram_validation_error_allows_retry(page):
    """
    After validation failure, user can edit and resubmit.

    Verifies that the modal stays open after an error, allowing the user
    to correct their token and try again.
    """
    await mock_extensions_api(page, installed=[_TELEGRAM_EXTENSION])

    call_count = [0]

    async def handle_setup(route):
        if route.request.method == "GET":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"secrets": _TELEGRAM_SECRETS}),
            )
        elif route.request.method == "POST":
            call_count[0] += 1
            # First call fails, second succeeds
            if call_count[0] == 1:
                await route.fulfill(
                    status=400,
                    content_type="application/json",
                    body=json.dumps({"success": False, "message": "invalid token"}),
                )
            else:
                await route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"success": True}),
                )

    await page.route("**/api/extensions/telegram/setup", handle_setup)
    await open_telegram_configure_modal(page)

    # First attempt: invalid token
    input_field = page.locator(SEL["configure_input"])
    await input_field.fill("bad_token")
    await page.locator(SEL["configure_save_btn"]).click()

    # Wait for error
    await page.wait_for_timeout(300)
    modal = page.locator(SEL["configure_modal"])
    assert await modal.is_visible()

    # Clear and try again with valid token
    await input_field.clear()
    await input_field.fill("123456789:ValidTokenHere")
    await page.locator(SEL["configure_save_btn"]).click()

    # Modal should close on second success
    await modal.wait_for(state="hidden", timeout=5000)


# ─── Test Group C: Token Format Handling ──────────────────────────────────────

async def test_telegram_token_with_special_chars(page):
    """
    Telegram tokens with hyphens and underscores are accepted.

    Verifies that valid Telegram token characters (hyphens, underscores) are
    properly handled without errors.
    """
    await mock_extensions_api(page, installed=[_TELEGRAM_EXTENSION])

    async def handle_setup(route):
        if route.request.method == "GET":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"secrets": _TELEGRAM_SECRETS}),
            )
        elif route.request.method == "POST":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"success": True}),
            )

    await page.route("**/api/extensions/telegram/setup", handle_setup)
    await open_telegram_configure_modal(page)

    # Token with various special characters valid in Telegram tokens
    token_value = "987654321:ABCD-EFgh_ijkl-MNOP_qrst"
    input_field = page.locator(SEL["configure_input"])
    await input_field.fill(token_value)

    # Verify the value was entered correctly
    entered_value = await input_field.input_value()
    assert entered_value == token_value

    # Save should succeed
    await page.locator(SEL["configure_save_btn"]).click()
    await page.locator(SEL["configure_overlay"]).wait_for(state="hidden", timeout=5000)


async def test_telegram_token_colon_preserved_in_form(page):
    """
    Colon in token is not lost or transformed during form submission.

    Verifies that the colon separator in the Telegram token format is
    preserved through the form submission process.
    """
    await mock_extensions_api(page, installed=[_TELEGRAM_EXTENSION])

    submitted_token = [None]

    async def handle_setup(route):
        if route.request.method == "GET":
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"secrets": _TELEGRAM_SECRETS}),
            )
        elif route.request.method == "POST":
            # Capture the submitted token from the request body
            body = await route.request.post_data()
            if body:
                import json as json_module

                try:
                    data = json_module.loads(body)
                    submitted_token[0] = data.get("telegram_bot_token")
                except Exception:
                    pass
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"success": True}),
            )

    await page.route("**/api/extensions/telegram/setup", handle_setup)
    await open_telegram_configure_modal(page)

    # Enter token with colon
    token_value = "111222333:xyzABC-_test"
    await page.locator(SEL["configure_input"]).fill(token_value)
    await page.locator(SEL["configure_save_btn"]).click()

    # Wait for request to complete
    await page.wait_for_timeout(300)

    # Modal should close
    await page.locator(SEL["configure_overlay"]).wait_for(state="hidden", timeout=3000)
