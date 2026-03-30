import asyncio
import os
import signal
import sys
import tempfile

from config.config import Config, HookConfig, HookTrigger
from tools.base import ToolResult


class HookSystem:
    def __init__(self, config: Config):
        self.config = config
        self.hooks: list[HookConfig] = []

        if self.config.hooks_enabled:
            # hook.enabled (for partcular hook, hooks_enabled -> system wide config)
            self.hooks = [hook for hook in self.config.hooks if hook.enabled]

    async def _run_hook(self, hook: HookConfig) -> None:
        if hook.command:
            # refer more in shell tool
            process = await asyncio.create_subprocess_exec(
                hook.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.config.cwd,
                env=os.environ.copy(),
                start_new_session=True
            )

            try:
                await asyncio.wait_for(
                    process.communicate(),
                    timeout=hook.timeout_sec
                )

            except asyncio.TimeoutError:
                if sys.platform != "win32":

                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
                await process.wait()

        elif hook.script:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:

    async def trigger_before_agent(self, user_message: str) -> None:
        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_AGENT:
                await self._run_hook(hook)
