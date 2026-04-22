from __future__ import annotations


class ExecutionListener:
    def start_suite(self, suite) -> None:
        pass

    def end_suite(self, suite, result) -> None:
        pass

    def start_case(self, case) -> None:
        pass

    def end_case(self, case, result) -> None:
        pass

    def start_step(self, step) -> None:
        pass

    def end_step(self, step, result) -> None:
        pass
