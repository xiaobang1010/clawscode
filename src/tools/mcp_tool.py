from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, create_model

from src.services.mcp_client import MCPClient
from src.tool import Tool, ToolResult

logger = logging.getLogger(__name__)


def _schema_to_pydantic(schema: dict, model_name: str = "DynamicInput") -> type[BaseModel]:
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    field_definitions = {}
    for prop_name, prop_schema in properties.items():
        prop_type = _resolve_type(prop_schema)
        if prop_name in required:
            field_definitions[prop_name] = (prop_type, ...)
        else:
            default = prop_schema.get("default", None)
            field_definitions[prop_name] = (prop_type, default)

    return create_model(model_name, **field_definitions)


def _resolve_type(prop_schema: dict) -> type:
    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
    }
    json_type = prop_schema.get("type", "string")

    if json_type == "array":
        return list
    if json_type == "object":
        return dict

    return type_map.get(json_type, str)


class MCPToolAdapter(Tool):
    def __init__(
        self,
        name: str,
        description: str,
        input_schema_dict: dict,
        client: MCPClient,
    ) -> None:
        self.name = name
        self.description = description
        self._schema_dict = input_schema_dict
        self._client = client
        self.input_schema = _schema_to_pydantic(
            input_schema_dict, model_name=f"{name}Input"
        )

    async def call(self, input: BaseModel, context: Any) -> ToolResult:
        try:
            arguments = input.model_dump() if hasattr(input, "model_dump") else {}
            output = await self._call_with_elicitation(self.name, arguments)
            return ToolResult(output=output)
        except Exception as e:
            return ToolResult(output=str(e), is_error=True)

    async def _call_with_elicitation(self, tool_name: str, arguments: dict) -> str:
        try:
            return await self._client.call_tool(tool_name, arguments)
        except Exception as e:
            error_str = str(e)
            if "elicitation" in error_str.lower() or "url" in error_str.lower() and "required" in error_str.lower():
                try:
                    from mcp import UrlElicitationRequiredError
                    if isinstance(e, UrlElicitationRequiredError):
                        return await self._handle_elicitation_error(e, tool_name, arguments)
                except ImportError:
                    pass

            elicitation_handler = self._client.elicitation_handler
            pending = elicitation_handler.get_pending()
            if pending:
                for req in pending:
                    result = await elicitation_handler.handle_elicitation(req)
                    logger.info(f"[MCP] 已处理 Elicitation: {req.elicitation_id}")
                return await self._client.call_tool(tool_name, arguments)

            raise

    async def _handle_elicitation_error(self, error: Any, tool_name: str, arguments: dict) -> str:
        elicitation_handler = self._client.elicitation_handler

        try:
            elicitations = error.elicitations
        except AttributeError:
            elicitations = []

        for elicitation in elicitations:
            from src.services.mcp_client import ElicitationRequest

            request = ElicitationRequest(
                message=getattr(elicitation, "message", "MCP 服务器需要确认"),
                url=getattr(elicitation, "url", ""),
                elicitation_id=getattr(elicitation, "elicitationId", ""),
                mode=getattr(elicitation, "mode", "url"),
            )
            await elicitation_handler.handle_elicitation(request)
            logger.info(f"[MCP] 已自动接受 Elicitation: {request.elicitation_id}")

        return await self._client.call_tool(tool_name, arguments)

    def get_openai_tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._schema_dict,
            },
        }
