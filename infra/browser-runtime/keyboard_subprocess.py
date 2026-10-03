"""Wait for X11 keyboard injection without leaving late input processes alive."""
import asyncio


async def communicate(process, timeout=2.0):
    # Keep the pipe reader alive while terminating/reaping on timeout or cancel.
    reader = asyncio.create_task(process.communicate())
    try:
        return await asyncio.wait_for(asyncio.shield(reader), timeout)
    except BaseException:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        while not reader.done():
            try:
                await asyncio.shield(reader)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        # Retrieve a pipe error without replacing the original failure.
        try:
            reader.result()
        except BaseException:
            pass
        raise
