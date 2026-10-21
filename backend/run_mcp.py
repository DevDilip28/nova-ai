from nova.mcp_server import mcp
from nova import store

if __name__ == "__main__":
    store.initialize()
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8001)
