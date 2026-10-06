"""Thin entry for the read-only MCP server (AIRD S1, FR-100).
All behaviour lives in cem_gw/mcp_server.py. Run:  python mcp_server.py
Env: CEM_MCP_GATEWAY, CEM_MCP_GATEWAY_TOKEN, CEM_MCP_TOKEN (required),
CEM_MCP_HOST (127.0.0.1), CEM_MCP_PORT (8090), CEM_MCP_RATE_PER_MIN (120).
"""
from cem_gw.mcp_server import main

if __name__ == "__main__":
    main()
