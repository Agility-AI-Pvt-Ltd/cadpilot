"""Narrow, audited MCP boundary for the documented neka-nat/freecad-mcp tools."""

import shlex
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, ClassVar

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import get_settings
from app.schemas import ToolResult


class FreeCADMCPClient:
    ALLOWED_TOOLS: ClassVar[set[str]] = {
        "create_document",
        "get_objects",
        "get_object",
        "get_async_status",
        "execute_code_headless",
    }

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[ClientSession]:
        settings = get_settings()
        params = StdioServerParameters(
            command=settings.mcp_server_command, args=shlex.split(settings.mcp_server_args)
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            yield session

    async def available_tools(self) -> list[str]:
        async with self._session() as session:
            tools = await session.list_tools()
            return [tool.name for tool in tools.tools if tool.name in self.ALLOWED_TOOLS]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name not in self.ALLOWED_TOOLS:
            return ToolResult(success=False, error=f"Tool '{name}' is not approved")
        try:
            async with self._session() as session:
                result = await session.call_tool(name, arguments)
            if result.isError:
                return ToolResult(success=False, error=self._text(result.content))
            return ToolResult(success=True, data={"content": self._text(result.content)})
        except Exception as exc:  # noqa: BLE001 - client/server availability is an expected deployment failure
            return ToolResult(success=False, error=f"FreeCAD MCP unavailable: {exc}")

    async def get_objects(self, document_name: str) -> ToolResult:
        return await self.call(
            "get_objects", {"document_name": document_name, "include_screenshot": False}
        )

    async def execute_headless(self, script: str, timeout: int = 120) -> ToolResult:
        # Script is built solely by CadScriptCompiler; LLM text is never accepted here.
        return await self.call(
            "execute_code_headless",
            {"code": script, "timeout": timeout, "include_screenshot": False},
        )

    @staticmethod
    def _text(content: list[Any]) -> str:
        return "\n".join(getattr(item, "text", str(item)) for item in content)


class CadScriptCompiler:
    """Compiles a validated operation into a fixed FreeCAD script template."""

    @staticmethod
    def create_box(
        *,
        name: str,
        length: float,
        width: float,
        height: float,
        x: float,
        y: float,
        z: float,
        fcstd_path: str,
        stl_path: str,
    ) -> str:
        values = [name, length, width, height, x, y, z, fcstd_path, stl_path]
        if any("\n" in str(value) for value in values):
            raise ValueError("Invalid CAD value")
        return f"""import FreeCAD as App, Part, Mesh
doc = App.newDocument("CadPilot")
obj = doc.addObject("Part::Box", {name!r})
obj.Label = {name!r}
obj.Length = {length!r}; obj.Width = {width!r}; obj.Height = {height!r}
obj.Placement.Base = App.Vector({x!r}, {y!r}, {z!r})
doc.recompute()
doc.saveAs({fcstd_path!r})
Mesh.export([obj], {stl_path!r})
print("CADPILOT_RESULT=" + __import__('json').dumps({{'objects': [{{'object_id': obj.Name, 'name': obj.Label, 'type': obj.TypeId, 'parameters': {{'length': obj.Length, 'width': obj.Width, 'height': obj.Height}}, 'placement': {{'x': obj.Placement.Base.x, 'y': obj.Placement.Base.y, 'z': obj.Placement.Base.z}}}}]}}, sort_keys=True))"""

    @staticmethod
    def inspect_document(fcstd_path: str) -> str:
        if "\n" in fcstd_path:
            raise ValueError("Invalid CAD path")
        return f"""import FreeCAD as App
import json
doc = App.openDocument({fcstd_path!r})
doc.recompute()
objects = []
for obj in doc.Objects:
    if not hasattr(obj, 'Shape') or obj.Shape.isNull():
        continue
    parameters = {{}}
    for key in ('Length', 'Width', 'Height', 'Radius', 'Angle'):
        if hasattr(obj, key):
            try:
                parameters[key.lower()] = float(getattr(obj, key))
            except (TypeError, ValueError):
                pass
    base = obj.Placement.Base
    objects.append({{
        'object_id': obj.Name,
        'name': obj.Label,
        'type': obj.TypeId,
        'parameters': parameters,
        'placement': {{'x': base.x, 'y': base.y, 'z': base.z}},
    }})
print('CADPILOT_STATE=' + json.dumps({{'objects': objects, 'feature_history': []}}, sort_keys=True))"""
