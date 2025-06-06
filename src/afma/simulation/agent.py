from typing import Optional, Any, Union
import litellm
from loguru import logger
import json

from mcp.types import TextContent, ImageContent, EmbeddedResource

from afma.mcp_parser import scan_mcp_config_file, get_client
from afma.simulation.environment import Environment, EnvironmentInterface, SimulatedEnvironment


SYSTEM_PROMPT_AGENT = (
    "Help the user with their question using the tools available to you. "
    "Before selecting tools, consider which approach would be most efficient - look for tools that can handle multiple operations at once rather than making repeated calls for similar tasks. "
    "Choose the most optimal tool for each situation, considering both effectiveness and efficiency. "
    "If you can't help or user behaves weirdly, explicitly say that you can't help. "
)

class Agent:
    def __init__(
        self, 
        llm_config: dict[str, Any], 
        environment: EnvironmentInterface
    ):
        self.llm_config = llm_config
        self.message_history: list[dict[str, str]] = []
        self.environment = environment
        self.tools = None

    def get_used_tools(self) -> list[str]:
        return [tool["name"] for tool in self.message_history if tool["role"] == "tool"]

    async def talk(self, user_message: Optional[str] = None) -> str:
        if not self.tools:
            self.tools = await self.environment.collect_resources()
            self.message_history = [{"role": "system", "content": SYSTEM_PROMPT_AGENT}]

        if user_message:
            self.message_history.append({"role": "user", "content": user_message})

        # Initial LLM call
        response = await litellm.acompletion(
            messages=self.message_history,
            tools=self.tools,
            **self.llm_config
        )
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        # Loop to handle multiple rounds of tool calls
        while tool_calls:
            self.message_history.append(response_message.json())

            for tool_call in tool_calls:
                tool_call_id = tool_call.id
                tool_call_name = tool_call.function.name
                tool_call_args = tool_call.function.arguments

                call_id, tool_call_result = await self.environment.call_tool(tool_call_name, tool_call_args, tool_call_id)

                # Add tool response with the corresponding tool_call_id
                self.message_history.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": tool_call_name,
                    "content": tool_call_result
                })

            # Get next response after tool calls
            response = await litellm.acompletion(
                messages=self.message_history,
                tools=self.tools,
                **self.llm_config
            )
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

        # Add the final assistant message to history
        self.message_history.append({"role": "assistant", "content": response_message.content})
        return response_message.content
