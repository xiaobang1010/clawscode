from __future__ import annotations

from typing import Any

from pydantic import BaseModel, create_model

from src.services.mcp_client import MCPClient
from src.tool import Tool, ToolResult


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
            output = await self._client.call_tool(self.name, arguments)
            return ToolResult(output=output)
        except Exception as e:
            return ToolResult(output=str(e), is_error=True)

    def get_openai_tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._schema_dict,
            },
        }
