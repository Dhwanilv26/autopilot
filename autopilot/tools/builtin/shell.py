import asyncio
from pathlib import Path
import os
from pydantic import BaseModel, Field
import fnmatch  # for pattern matching in unix- type file names
from autopilot.tools.base import Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult
import sys
import signal

from autopilot.utils.paths import resolve_path
BLOCKED_COMMANDS = {
    "rm -rf /",
    "rm -rf ~",
    "rm -rf /*",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    "mkfs",
    "fdisk",
    "parted",
    ":(){ :|:& };:",  # Fork bomb
    "chmod 777 /",
    "chmod -R 777",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
}


def is_blocked_command(command: str) -> bool:

    for blocked in BLOCKED_COMMANDS:  # to traverse in set of strings
        if blocked in command:  # in in strings checks for substrings too
            return True

    return False


class ShellParams(BaseModel):
    command: str = Field(...,
                         description="The shell command to execute")
    timeout: int = Field(120, ge=1, le=600, description="Timeout in seconds (default:120)")
    cwd: str | None = Field(None, description="Working directory for the command")


class ShellTool(Tool):
    name = "shell"
    kind = ToolKind.SHELL
    description = "Execute a shell command. Use this for running system commands, scripts and CLI tools."

    @property
    def schema(self):
        return ShellParams

    async def get_confirmation(self, invocation: ToolInvocation) -> ToolConfirmation | None:
        params = ShellParams(**invocation.params)

        if is_blocked_command(params.command):
            return ToolConfirmation(
                tool_name=self.name,
                params=invocation.params,
                description=f"Execute (BLOCKED) : {params.command}",
                command=params.command,
                is_dangerous=True

            )

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"execute command: {params.command}",
            command=params.command,
            is_dangerous=False
        )

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ShellParams(**invocation.params)
        command = params.command.lower().strip()
        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                return ToolResult.error_result(
                    f"Command blocked for safety : {params.command}",
                    metadata={"blocked": True}
                )

        if params.cwd:
            cwd = Path(params.cwd)
            if not cwd.is_absolute():
                cwd = invocation.cwd/cwd  # append the absolute with relative to get new absolute

        else:
            cwd = invocation.cwd

        if not cwd.exists():
            return ToolResult.error_result(f"Working directory doesn't exist : {cwd}")

        env = self._build_environment()

        if sys.platform == "win32":
            shell_cmd = ["cmd.exe", "/c", params.command]
        else:
            shell_cmd = ["/bin/bash", "-c", params.command]
            # to launch a bash shell to execute the command string directly
            # background mai yeh sab chalta rehega, our main terminal gets the output via piping

        process = await asyncio.create_subprocess_exec(
            # use * to destructure/unpack list,
            # ** to unpack dictionary or kwargs
            *shell_cmd,
            # processes communicate with pipes, (ek ka output is dusre ka input)
            stdout=asyncio.subprocess.PIPE,  # capture the output instead of printing it in the terminal
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True
        )

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
                # waits for the process to finish and collects all outputs and errors
                timeout=params.timeout
            )
        except asyncio.TimeoutError:
            if sys.platform != "win32":
                # unix (mac/linux) supports process groups, so have to kill the entire process grp, other wise problem of orphan processes occurs
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                # windows doesnt support process grps, so seedha process ko hi udado
                process.kill()
            await process.wait()
            return ToolResult.error_result(f"command timed out after {params.timeout}s")

        # decode is needed because process output arrives in bytes we need it in text
        stdout = stdout_data.decode("utf-8", errors="replace")
        stderr = stderr_data.decode("utf-8", errors="replace")
        # replace se invalid bytes become '?' emoji.. so UnicodeDecodeError is not thrown
        exit_code = process.returncode

        output = ""
        if stdout.strip():
            output += stdout.rstrip()

        if stderr.strip():
            output += "\n--- stderr ---\n"
            output += stderr.strip()

        if exit_code != 0:
            output += f"\nExit code : {exit_code}"

        if len(output) > 100*1024:  # limiting output to 100KB only
            output = output[:100*1024] + "\n... [output truncated]"

        return ToolResult(
            output=output,
            success=exit_code == 0,
            error=stderr if exit_code != 0 else None,
            exit_code=exit_code
        )

    def _build_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        shell_environment = self.config.shell_environment

        if not shell_environment.ignore_default_excludes:
            for pattern in shell_environment.exclude_patterns:
                keys_to_remove = [k for k in env.keys() if fnmatch.fnmatch(
                    k.upper(), pattern.upper())]
                # to match SECRET_KEY with KEY, upper is used as generally env variables are stored in uppercase

                for k in keys_to_remove:
                    del env[k]

        if shell_environment.set_vars:
            # to update the env variables based on our needs for the specific env, set this up in the config.toml file
            env.update(shell_environment.set_vars)

        return env
