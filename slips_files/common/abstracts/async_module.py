# SPDX-FileCopyrightText: 2021 Sebastian Garcia <sebastian.garcia@agents.fel.cvut.cz>
# SPDX-License-Identifier: GPL-2.0-only
import asyncio
from asyncio import Task
from typing import (
    Callable,
    List,
)
from slips_files.common.abstracts.module import IModule


class AsyncModule(IModule):
    """
    An abstract class for asynchronous slips modules
    """

    name = "AsyncModule"

    def __init__(self, *args, **kwargs):
        IModule.__init__(self, *args, **kwargs)
        # list of async functions to await before flowalerts shuts down
        self.tasks: List[Task] = []

    def init(self, **kwargs): ...

    def create_task(self, func, *args) -> Task:
        """
        wrapper for asyncio.create_task
        The goal here is to add a callback to tasks to be able to handle
        exceptions. because asyncio Tasks do not raise exceptions
        """
        task = asyncio.create_task(func(*args))
        task.add_done_callback(self.handle_exception)

        # Allow the event loop to run the scheduled task
        # await asyncio.sleep(0)

        # to wait for these functions before flowalerts shuts down
        self.tasks.append(task)
        return task

    def handle_exception(self, task):
        """
        in asyncmodules we use Async.Task to run some of the functions
        If an exception occurs in a coroutine that was wrapped in a Task
        (e.g., asyncio.create_task), the exception does not crash the program
         but remains in the task.
        This function is used to handle the exception in the task
        """
        try:
            # Access task result to raise the exception if it occurred
            task.result()
        except Exception as e:
            self.print(e, 0, 1)

    async def main(self): ...

    async def shutdown_gracefully(self):
        """Implement the async shutdown logic here"""
        pass

    async def run_main(self):
        return await self.main()

    @staticmethod
    def run_async_function(func: Callable):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(func())

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            error: bool = self.pre_main()
            if error or self.should_stop():
                self.run_async_function(self.shutdown_gracefully)
                return
        except KeyboardInterrupt:
            self.run_async_function(self.shutdown_gracefully)
            return
        except Exception:
            self.print_traceback()
            return

        while True:
            try:
                if self.should_stop():
                    self.run_async_function(self.shutdown_gracefully)
                    return

                # if a module's main() returns 1, it means there's an
                # error and it needs to stop immediately
                error: bool = self.run_async_function(self.run_main)
                if error:
                    self.run_async_function(self.shutdown_gracefully)
                    return

            except KeyboardInterrupt:
                self.keyboard_int_ctr += 1
                if self.keyboard_int_ctr >= 2:
                    # on the second ctrl+c Slips immediately stop
                    return True
                # on the first ctrl + C keep looping until the should_stop()
                # returns true
                continue
            except Exception:
                self.print_traceback()
                return
