#!/usr/bin/env python3
"""
Test script to connect to an MCP server and list available tools.

Prerequisites:
    Install dependencies first:
        poetry install
    OR
        pip install mcp httpx anyio

Usage:
    python test_mcp_server.py --url http://example.com:8000/mcp --mode streamable-http --header "Authorization: Bearer token"
    python test_mcp_server.py --url http://example.com:8000/sse --mode sse --header "Authorization: Bearer token"
"""

import asyncio
import argparse
import logging
import sys
from datetime import timedelta
from typing import Optional, Dict

try:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamablehttp_client
except ImportError as e:
    print("ERROR: MCP library not found. Please install dependencies:")
    print("  poetry install")
    print("  OR")
    print("  pip install mcp httpx anyio")
    print(f"\nOriginal error: {e}")
    sys.exit(1)

try:
    from holmes.common.env_vars import SSE_READ_TIMEOUT
except ImportError:
    # Fallback if running outside the project structure
    import os
    SSE_READ_TIMEOUT = float(os.environ.get("SSE_READ_TIMEOUT", "120"))

# Convert SSE_READ_TIMEOUT to timedelta if it's a float
if isinstance(SSE_READ_TIMEOUT, (int, float)):
    SSE_READ_TIMEOUT_TD = timedelta(seconds=SSE_READ_TIMEOUT)
else:
    SSE_READ_TIMEOUT_TD = SSE_READ_TIMEOUT

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_headers(header_strings: list) -> Optional[Dict[str, str]]:
    """Parse header strings like 'Key: Value' into a dict."""
    if not header_strings:
        return None
    
    headers = {}
    for header_str in header_strings:
        if ':' in header_str:
            key, value = header_str.split(':', 1)
            headers[key.strip()] = value.strip()
        else:
            logger.warning(f"Invalid header format: {header_str}. Expected 'Key: Value'")
    return headers


async def test_sse_connection(url: str, headers: Optional[Dict[str, str]] = None):
    """Test SSE connection to MCP server."""
    logger.info(f"🔍 Testing SSE connection to: {url}")
    if headers:
        logger.info(f"🔍 Headers: {list(headers.keys())}")
    
    try:
        async with sse_client(
            url,
            headers,
            sse_read_timeout=SSE_READ_TIMEOUT_TD,
        ) as (read_stream, write_stream):
            logger.info("✅ SSE connection established")
            async with ClientSession(read_stream, write_stream) as session:
                logger.info("🔍 Initializing session...")
                init_result = await session.initialize()
                logger.info(f"✅ Session initialized: {init_result}")
                
                logger.info("🔍 Calling list_tools()...")
                tools_result = await session.list_tools()
                
                tool_count = len(tools_result.tools) if tools_result and hasattr(tools_result, 'tools') else 0
                logger.info(f"✅ list_tools() returned {tool_count} tool(s)")
                
                if tools_result and hasattr(tools_result, 'tools') and tools_result.tools:
                    logger.info("📋 Available tools:")
                    for tool in tools_result.tools:
                        logger.info(f"  - {tool.name}: {tool.description or 'No description'}")
                else:
                    logger.warning("⚠️ No tools found")
                
                return tools_result
    except Exception as e:
        logger.error(f"❌ SSE connection failed: {type(e).__name__}: {e}", exc_info=True)
        raise


async def test_streamable_http_connection(url: str, headers: Optional[Dict[str, str]] = None):
    """Test Streamable HTTP connection to MCP server."""
    logger.info(f"🔍 Testing Streamable HTTP connection to: {url}")
    if headers:
        logger.info(f"🔍 Headers: {list(headers.keys())}")
    
    try:
        async with streamablehttp_client(
            url,
            headers=headers,
            sse_read_timeout=SSE_READ_TIMEOUT_TD,
        ) as (read_stream, write_stream, _):
            logger.info("✅ Streamable HTTP connection established")
            async with ClientSession(read_stream, write_stream) as session:
                logger.info("🔍 Initializing session...")
                init_result = await session.initialize()
                logger.info(f"✅ Session initialized: {init_result}")
                
                logger.info("🔍 Calling list_tools()...")
                tools_result = await session.list_tools()
                
                tool_count = len(tools_result.tools) if tools_result and hasattr(tools_result, 'tools') else 0
                logger.info(f"✅ list_tools() returned {tool_count} tool(s)")
                
                if tools_result and hasattr(tools_result, 'tools') and tools_result.tools:
                    logger.info("📋 Available tools:")
                    for tool in tools_result.tools:
                        logger.info(f"  - {tool.name}: {tool.description or 'No description'}")
                else:
                    logger.warning("⚠️ No tools found")
                
                return tools_result
    except Exception as e:
        logger.error(f"❌ Streamable HTTP connection failed: {type(e).__name__}: {e}", exc_info=True)
        raise


async def main():
    parser = argparse.ArgumentParser(description='Test MCP server connection')
    parser.add_argument('--url', required=True, help='MCP server URL')
    parser.add_argument('--mode', choices=['sse', 'streamable-http'], default='streamable-http',
                       help='Connection mode (default: streamable-http)')
    parser.add_argument('--header', action='append', dest='headers',
                       help='HTTP header in format "Key: Value" (can be used multiple times)')
    parser.add_argument('--verify-ssl', action='store_true', default=True,
                       help='Verify SSL certificates (default: True)')
    parser.add_argument('--no-verify-ssl', dest='verify_ssl', action='store_false',
                       help='Do not verify SSL certificates')
    
    args = parser.parse_args()
    
    headers = parse_headers(args.headers) if args.headers else None
    
    logger.info("=" * 80)
    logger.info("MCP Server Connection Test")
    logger.info("=" * 80)
    logger.info(f"URL: {args.url}")
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Verify SSL: {args.verify_ssl}")
    logger.info("=" * 80)
    
    try:
        if args.mode == 'sse':
            await test_sse_connection(args.url, headers)
        else:
            await test_streamable_http_connection(args.url, headers)
        
        logger.info("=" * 80)
        logger.info("✅ Test completed successfully")
        logger.info("=" * 80)
        return 0
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ Test failed: {e}")
        logger.error("=" * 80)
        return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
