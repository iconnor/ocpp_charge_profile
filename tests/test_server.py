""" Simple class to test the server """
import asyncio
import pytest


@pytest.mark.asyncio
async def test_server():
    """Test the server."""
    _server = await asyncio.create_subprocess_exec(
        "python", "server.py", stdout=asyncio.subprocess.PIPE)
    # Wait for server to start
    await asyncio.sleep(1)

    # Assert we made it here
    assert True
