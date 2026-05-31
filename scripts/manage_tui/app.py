"""Textual application: environment switcher, per-profile action rows,
command preview, and a streaming output log.

Focus an action button to preview the exact command(s); press it to run.
The preview is produced by commands.build_sequence and the same objects are
handed to the runner, so the preview is always what executes.
"""

from __future__ import annotations

import asyncio
import os
import subprocess

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Footer, Header, RichLog, Static

from . import compose as compose_mod
from .commands import ACTIONS, ALL, TESTS, build_scrape_site, build_sequence, build_test
from .config_view import load_config_summary, masked_env
from .model import Manifest
from .runner import SequenceRunner

_SUMMARY_ENV_KEYS = (
    "MONGO_ROOT_USER",
    "MONGO_ROOT_PASSWORD",
    "DISCORD_CHANNEL_ID",
    "DISCORD_BOT_TOKEN",
)
_PREVIEW_HINT = "(focus an action — Tab/arrows — to preview its command)"

# Test button labels. Keys must match commands.TESTS; ids are f"test-{key}".
# scrape/mongo run against scraper-mcp; cron/discord run against bot.
_TEST_LABELS = {
    "scrape": "Scrape",
    "mongo": "Mongo",
    "cron": "Cron",
    "discord": "Discord",
}


class ManagerApp(App):
    CSS = """
    Screen { layout: vertical; }

    /* Buttons default to height 3 in Textual; flattened to a single row so the
       control panels stay compact and never starve #log of vertical space.
       Default-height buttons were the bug: on a normal-height terminal the
       panels above consumed every row and the log collapsed / scrolled off. */
    Button { height: 1; min-width: 9; margin: 0 1 0 0; border: none; }
    Button:focus { text-style: reverse; }

    #envbar { height: 1; padding: 0 1; }

    /* summary + preview side by side, capped and internally scrollable so a
       long summary can never push the log off-screen on small terminals. */
    #top { height: auto; max-height: 11; }
    #summary { width: 1fr; height: auto; max-height: 11; overflow-y: auto;
               border: round $accent; padding: 0 1; margin: 0 1 0 0; }
    #preview { width: 1fr; height: auto; max-height: 11; overflow-y: auto;
               border: round $secondary; padding: 0 1; }

    #profiles { height: auto; max-height: 8; overflow-y: auto;
                border: round $primary; padding: 0 1; }
    .scope-row { height: 1; }
    .scope-label { width: 18; height: 1; content-align: left middle; }

    /* tests + scrape side by side to save one vertical row. */
    #bottom { height: auto; }
    #tests { height: auto; width: 1fr; border: round $warning; padding: 0 1; }
    #scrape { height: auto; width: 1fr; border: round $success; padding: 0 1; }

    /* The log takes the remaining space but is guaranteed a usable minimum so
       command output is always visible. */
    #log { height: 1fr; min-height: 5; border: round $panel; }
    """

    BINDINGS = [
        ("q", "quit_clean", "Quit"),
        ("ctrl+c", "quit_clean", "Quit"),
        ("c", "cancel", "Cancel run"),
        ("r", "refresh_status", "Status (all)"),
        ("x", "clear_log", "Clear output"),
        ("ctrl+l", "clear_log", "Clear output"),
        ("f", "toggle_log", "Log fullscreen"),
        ("ctrl+y", "copy_log", "Copy log"),
    ]

    def __init__(self, manifest: Manifest) -> None:
        super().__init__()
        self.manifest = manifest
        self.env_name = manifest.default_environment
        self.runner = SequenceRunner()
        self.profile_map = compose_mod.parse_profiles(self.env.compose_files)
        self._log_buffer: list[str] = []

    @property
    def env(self):
        return self.manifest.environments[self.env_name]

    # ---- composition -------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Horizontal(
            *(Button(name, id=f"env-{name}") for name in self.manifest.environments),
            id="envbar",
        )
        yield Horizontal(
            Static(id="summary"),
            Static(_PREVIEW_HINT, id="preview"),
            id="top",
        )
        yield VerticalScroll(*self._row_widgets(), id="profiles")
        yield Horizontal(
            Horizontal(*self._test_widgets(), id="tests"),
            Horizontal(*self._scrape_widgets(), id="scrape"),
            id="bottom",
        )
        yield RichLog(id="log", highlight=False, markup=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._render_summary()
        self._update_env_buttons()
        self.query_one("#log", RichLog).write(
            "Docker manager ready. Tab to an action to preview it; Enter runs it."
        )

    # ---- row construction --------------------------------------------------
    def _scopes(self) -> list[str]:
        return [ALL, *sorted(self.profile_map.keys())]

    def _row_widgets(self) -> list[Horizontal]:
        rows: list[Horizontal] = []
        for scope in self._scopes():
            children: list[Static | Button] = [
                Static(self._row_label(scope), classes="scope-label")
            ]
            children += [
                Button(self._button_label(scope, action), id=f"act-{scope}-{action}")
                for action in ACTIONS
            ]
            rows.append(Horizontal(*children, classes="scope-row"))
        return rows

    def _row_label(self, scope: str) -> str:
        if scope == "bot" and self.env.config_merge is not None:
            return "bot (idles in dev)"
        return scope

    @staticmethod
    def _button_label(scope: str, action: str) -> str:
        if action == "stop":
            return "Down" if scope == ALL else "Stop"
        return action.capitalize()

    def _test_widgets(self) -> list[Static | Button]:
        children: list[Static | Button] = [Static("tests", classes="scope-label")]
        children += [Button(_TEST_LABELS[test], id=f"test-{test}") for test in TESTS]
        return children

    def _scrape_widgets(self) -> list[Static | Button]:
        cfg = load_config_summary(self.env, masked_env())
        children: list[Static | Button] = [Static("scrape site:", classes="scope-label")]
        children += [Button(site, id=f"scrape-{site}") for site in sorted(cfg.enabled_sites)]
        return children

    # ---- events ------------------------------------------------------------
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("env-"):
            await self._switch_env(button_id[len("env-") :])
        elif button_id.startswith("act-"):
            _, scope, action = button_id.split("-", 2)
            self._run_action(scope, action)
        elif button_id.startswith("test-"):
            self._run_test(button_id[len("test-") :])
        elif button_id.startswith("scrape-"):
            self._run_scrape_site(button_id[len("scrape-") :])

    def on_descendant_focus(self, event) -> None:
        widget = getattr(event, "widget", None) or getattr(event, "control", None)
        widget_id = getattr(widget, "id", None) or ""
        if widget_id.startswith("act-"):
            _, scope, action = widget_id.split("-", 2)
            self._preview(scope, action)
        elif widget_id.startswith("test-"):
            self._preview_test(widget_id[len("test-") :])
        elif widget_id.startswith("scrape-"):
            self._preview_scrape(widget_id[len("scrape-") :])

    # ---- actions -----------------------------------------------------------
    def _run_action(self, scope: str, action: str) -> None:
        if self.runner.is_running:
            self._log("! a command is already running — press 'c' to cancel it first")
            return
        sequence = build_sequence(self.env, scope, action, self.profile_map)
        self._preview(scope, action)
        self.run_worker(self._execute(sequence, action), exclusive=True, group="runner")

    def _run_scrape_site(self, site: str) -> None:
        if self.runner.is_running:
            self._log("! a command is already running — press 'c' to cancel it first")
            return
        sequence = build_scrape_site(site)
        self._preview_scrape(site)
        self.run_worker(self._execute(sequence, "test"), exclusive=True, group="runner")

    def _run_test(self, test: str) -> None:
        if self.runner.is_running:
            self._log("! a command is already running — press 'c' to cancel it first")
            return
        sequence = build_test(test)
        self._preview_test(test)
        # action != "start", so _execute skips the proxy-down warn path.
        self.run_worker(self._execute(sequence, "test"), exclusive=True, group="runner")

    async def _execute(self, sequence, action: str) -> None:
        if action == "start" and self.env.proxy is not None:
            await self._warn_if_proxy_down()
        log = self.query_one("#log", RichLog)

        def _write(line: str) -> None:
            self._log_buffer.append(str(line))
            log.write(line)

        await self.runner.run(sequence, _write)

    async def _warn_if_proxy_down(self) -> None:
        host, port = _split_host_port(self.env.proxy.check_url)
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=2.0)
            writer.close()
        except (TimeoutError, OSError, ValueError):
            self._log(
                f"! proxy not reachable at {host}:{port} — "
                "start it or the scraper will fail (continuing anyway)"
            )

    async def action_quit_clean(self) -> None:
        await self.runner.cancel()
        self.exit()

    async def action_cancel(self) -> None:
        if self.runner.is_running:
            self._log("... cancelling (an in-flight build continues inside Docker)")
            await self.runner.cancel()
        else:
            self._log("(nothing running)")

    def action_refresh_status(self) -> None:
        self._run_action(ALL, "status")

    def action_clear_log(self) -> None:
        self._log_buffer.clear()
        self.query_one("#log", RichLog).clear()

    def action_toggle_log(self) -> None:
        is_visible = self.query_one("#top").display
        for widget_id in ("top", "profiles", "bottom"):
            self.query_one(f"#{widget_id}").display = not is_visible

    def action_copy_log(self) -> None:
        if not self._log_buffer:
            self._log("(log is empty)")
            return
        content = "\n".join(self._log_buffer)
        try:
            if os.environ.get("WAYLAND_DISPLAY"):
                subprocess.run(["wl-copy"], input=content.encode(), check=True, timeout=3)
            else:
                subprocess.run(
                    ["xclip", "-sel", "clip"], input=content.encode(), check=True, timeout=3
                )
            self._log(f"✓ copied {len(self._log_buffer)} lines to clipboard")
        except FileNotFoundError as exc:
            self._log(f"! clipboard tool not found: {exc.filename} — install wl-clipboard or xclip")
        except Exception as exc:
            self._log(f"! copy failed: {exc}")

    # ---- environment switch ------------------------------------------------
    async def _switch_env(self, name: str) -> None:
        if name == self.env_name or name not in self.manifest.environments:
            return
        if self.runner.is_running:
            self._log("! stop the running command before switching environment")
            return
        self.env_name = name
        self.profile_map = compose_mod.parse_profiles(self.env.compose_files)
        container = self.query_one("#profiles", VerticalScroll)
        await container.remove_children()
        await container.mount(*self._row_widgets())
        scrape_container = self.query_one("#scrape", Horizontal)
        await scrape_container.remove_children()
        await scrape_container.mount(*self._scrape_widgets())
        self._render_summary()
        self._update_env_buttons()
        self._set_preview(_PREVIEW_HINT)
        self._log(f"— switched to environment: {name}")

    def _update_env_buttons(self) -> None:
        for name in self.manifest.environments:
            button = self.query_one(f"#env-{name}", Button)
            button.variant = "success" if name == self.env_name else "default"

    # ---- rendering helpers -------------------------------------------------
    def _preview(self, scope: str, action: str) -> None:
        sequence = build_sequence(self.env, scope, action, self.profile_map)
        self._set_preview("\n".join(command.preview() for command in sequence))

    def _preview_test(self, test: str) -> None:
        sequence = build_test(test)
        self._set_preview("\n".join(command.preview() for command in sequence))

    def _preview_scrape(self, site: str) -> None:
        sequence = build_scrape_site(site)
        self._set_preview("\n".join(cmd.preview() for cmd in sequence))

    def _set_preview(self, text: str) -> None:
        self.query_one("#preview", Static).update(text)

    def _render_summary(self) -> None:
        env = self.env
        env_vars = masked_env()
        cfg = load_config_summary(env, env_vars)
        lines = [
            f"[b]env:[/b] {env.name} — {env.description}",
            f"[b]compose:[/b] {' '.join(env.compose_files)}",
            f"[b]config:[/b] {cfg.source_label}",
            f"[b]keywords:[/b] {', '.join(cfg.keywords) or '(none)'}",
            f"[b]sites:[/b] {', '.join(cfg.enabled_sites) or '(none)'}",
            f"[b]proxy:[/b] {cfg.proxy}",
            f"[b]mongo:[/b] {cfg.mongo_db} / {cfg.mongo_collection}",
        ]
        for key in _SUMMARY_ENV_KEYS:
            if key in env_vars:
                lines.append(f"[b]{key}:[/b] {env_vars[key]}")
        self.query_one("#summary", Static).update("\n".join(lines))

    def _log(self, message: str) -> None:
        self._log_buffer.append(message)
        self.query_one("#log", RichLog).write(message)


def _split_host_port(url: str) -> tuple[str, int]:
    """'socks5://localhost:1080' -> ('localhost', 1080)."""
    without_scheme = url.split("://", 1)[-1]
    host, _, port = without_scheme.partition(":")
    return host or "localhost", int(port or "1080")
