import asyncio

# MCP Python SDK（fastmcp 的依赖里通常带了 mcp 包）
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession


MCP_URL = "http://127.0.0.1:8001/mcp"  # 对应你 mcp.run(... path="/mcp")

async def main():
    async with streamablehttp_client(MCP_URL) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            # 1) 初始化握手
            await session.initialize()

            # 2) 列出 tools（确认 hotel_search 暴露成功）
            tools = await session.list_tools()
            print("\n=== tools ===")
            for t in tools.tools:
                print("-", t.name)

            # 3) 调用你的 tool：hotel_search
            print("\n=== call hotel_search ===")
            # result = await session.call_tool("hotel_search", {"hotel_name": ["汉庭酒店(包头民族东路店)", "北京香江意舍酒店"]})
            res = await session.call_tool("adp_chat_sse", {
                "content": "我要去杭州西湖玩",
                "session_id": "a29bae68-cb1c-489d-8097-6be78f136acf",
                "visitor_biz_id": "2004001099116640832",
                "streaming_throttle": 10
            })
            print(res)
            # print(result)

if __name__ == "__main__":
    asyncio.run(main())
