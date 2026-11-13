"""Explicit API launcher; use --with-bot only for a configured Telegram account."""
import argparse
import asyncio
from pathlib import Path
import sys

async def run(with_bot):
    root = Path(__file__).resolve().parent
    processes = []
    try:
        processes.append(await asyncio.create_subprocess_exec(sys.executable, '-m', 'uvicorn',
            'main:app', '--app-dir', str(root/'fastapi'), '--host','127.0.0.1','--port','8000'))
        if with_bot:
            processes.append(await asyncio.create_subprocess_exec(sys.executable,str(root/'bot.py')))
        tasks = [asyncio.create_task(process.wait()) for process in processes]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    finally:
        for process in processes:
            if process.returncode is None:
                process.terminate()
        await asyncio.gather(*(process.wait() for process in processes))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--with-bot', action='store_true')
    args = parser.parse_args()
    try:
        asyncio.run(run(args.with_bot))
    except KeyboardInterrupt:
        pass
