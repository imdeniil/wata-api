import asyncio
from wata import Client

client = Client(base_url="https://api.wata.pro/", jwt_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJQdWJsaWNJZCI6IjNhMTg5NjY2LWVkZDItNTE5MS1kYjY4LTMzOTVkZDA0ZGFmYSIsIlRva2VuVmVyc2lvbiI6IjIiLCJleHAiOjE3NzM1ODY1MDcsImlzcyI6Imh0dHBzOi8vYXBpLndhdGEucHJvIiwiYXVkIjoiaHR0cHM6Ly9hcGkud2F0YS5wcm8vYXBpL2gyaCJ9.V_8di5g5cGOMRKrfcJXa7qoSwvBIBhlG6ClGr62MHtI")

async def main():

    async with client:
        result = await client.payments.get_link_by_uuid(uuid="3a18cde2-07df-7810-f6b7-7df9c2d0ee87")
        print(result)

asyncio.run(main())