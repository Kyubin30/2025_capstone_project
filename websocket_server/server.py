import os, asyncio, json
from motor.motor_asyncio import AsyncIOMotorClient
import websockets

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB  = os.getenv("DB_NAME", "news_database")
COL = os.getenv("COLLECTION_NAME", "news_data")
PORT = int(os.getenv("WS_PORT", "8000"))

mongo = AsyncIOMotorClient(MONGO_URI)
col = mongo[DB][COL]

send_tasks = {}

async def send_random_every(ws, interval=5):
    while True:
        cursor = col.aggregate([{"$sample": {"size": 1}}])
        docs = await cursor.to_list(length=1)
        if docs:
            d = docs[0]
            d["_id"] = str(d["_id"])
            await ws.send(json.dumps(d, ensure_ascii=False, default=str))
        await asyncio.sleep(interval)

async def handler(ws):
    try:
        async for msg in ws:
            cmd = msg.strip().upper()
            if cmd.startswith("START"):
                try: interval = int(cmd.split(",")[1])
                except: interval = 5
                t = send_tasks.get(ws)
                if t and not t.done(): t.cancel()
                send_tasks[ws] = asyncio.create_task(send_random_every(ws, interval))
                await ws.send(json.dumps({"status":"started","interval":interval}))
            elif cmd.startswith("STOP"):
                t = send_tasks.get(ws)
                if t and not t.done(): t.cancel()
                await ws.send(json.dumps({"status":"stopped"}))
            else:
                await ws.send(json.dumps({"status":"unknown_command","echo":msg}))
    except websockets.ConnectionClosed:
        pass
    finally:
        t = send_tasks.pop(ws, None)
        if t and not t.done(): t.cancel()

async def main():
    srv = await websockets.serve(handler, "0.0.0.0", PORT, ping_interval=20, ping_timeout=20)
    print(f"WS listening on :{PORT}")
    await srv.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
