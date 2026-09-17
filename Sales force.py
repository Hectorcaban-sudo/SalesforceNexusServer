import os
import json
import asyncio
import requests
from dotenv import load_dotenv
from openai import OpenAI
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SF_INSTANCE_URL = os.getenv("SF_INSTANCE_URL").rstrip('/')
SF_CLIENT_ID = os.getenv("SF_CLIENT_ID")
SF_CLIENT_SECRET = os.getenv("SF_CLIENT_SECRET")

openai_client = OpenAI(api_key=OPENAI_API_KEY)


def get_salesforce_oauth_token() -> str:
    """Authenticates to Salesforce using OAuth 2.0 Client Credentials Flow."""
    token_url = f"{SF_INSTANCE_URL}/services/oauth2/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": SF_CLIENT_ID,
        "client_secret": SF_CLIENT_SECRET
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    response = requests.post(token_url, data=payload, headers=headers)
    if response.status_code != 200:
        raise Exception(f"OAuth Authentication Failed: {response.text}")

    return response.json().get("access_token")


def convert_mcp_tools_to_openai(mcp_tools):
    """Converts MCP tool definitions to OpenAI tool specification."""
    openai_tools = []
    for tool in mcp_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        })
    return openai_tools


async def run_headless_360_query(user_prompt: str):
    # Step 1: Obtain OAuth Access Token
    print("🔑 Authenticating with Salesforce OAuth...")
    access_token = get_salesforce_oauth_token()

    # Hosted Headless 360 MCP SSE Endpoint URL
    mcp_endpoint = f"{SF_INSTANCE_URL}/services/mcp/headless-360/sse"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "text/event-stream"
    }

    print(f" Connecting to Hosted Headless 360 MCP: {mcp_endpoint}...")

    # Step 2: Establish SSE Connection with Hosted MCP Server
    async with sse_client(mcp_endpoint, headers=headers) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Retrieve Headless 360 Tools (Discover, Describe, Dispatch, Dispatch_Readonly)
            mcp_tools_res = await session.list_tools()
            tools = convert_mcp_tools_to_openai(mcp_tools_res.tools)

            print(f"\n User Query: '{user_prompt}'")

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are connected to Salesforce's Headless 360 MCP Server. "
                        "Use the provided `Discover` tool first to locate required capability skills, "
                        "`Describe` to get parameter definitions if needed, and `Dispatch` / `Dispatch_Readonly` "
                        "to execute actions."
                    )
                },
                {"role": "user", "content": user_prompt}
            ]

            # Step 3: Run Tool Execution Loop
            while True:
                response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )

                response_message = response.choices[0].message
                messages.append(response_message)

                # Check if LLM wants to call a Headless 360 Tool
                if response_message.tool_calls:
                    tool_call = response_message.tool_calls[0]
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    print(f"\n LLM calling Headless 360 Tool: `{tool_name}`")
                    print(f" Arguments: {json.dumps(tool_args, indent=2)}")

                    # Execute the tool against Hosted Salesforce MCP Server
                    result = await session.call_tool(tool_name, tool_args)

                    result_text = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content)

                    # Return result back to LLM context
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_text
                    })
                else:
                    # Final response from model
                    print("\n Final Answer:")
                    print(response_message.content)
                    break

if __name__ == "__main__":
    prompt = "give me the top 5 contracts"
    asyncio.run(run_headless_360_query(prompt))
