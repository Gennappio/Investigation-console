"""Translation of SLURM job states into the platform's job states.

SLURM reports more states than the platform distinguishes, and `sacct` decorates
some of them (``CANCELLED by 1000``). Anything unrecognised is reported as
pending rather than guessed at: a wrong terminal state would close a run that is
still executing.
"""

from __future__ import annotations

from lab_domain.execution import JobState

_STATES = {
    "PENDING": JobState.PENDING,
    "CONFIGURING": JobState.PENDING,
    "REQUEUED": JobState.PENDING,
    "RESIZING": JobState.PENDING,
    "SUSPENDED": JobState.PENDING,
    "RUNNING": JobState.RUNNING,
    "COMPLETING": JobState.RUNNING,
    "STAGE_OUT": JobState.RUNNING,
    "COMPLETED": JobState.COMPLETED,
    "CANCELLED": JobState.CANCELLED,
    "TIMEOUT": JobState.TIMED_OUT,
    "FAILED": JobState.FAILED,
    "BOOT_FAIL": JobState.FAILED,
    "DEADLINE": JobState.FAILED,
    "NODE_FAIL": JobState.FAILED,
    "OUT_OF_MEMORY": JobState.FAILED,
    "PREEMPTED": JobState.FAILED,
    "REVOKED": JobState.FAILED,
    "SPECIAL_EXIT": JobState.FAILED,
}


def job_state(reported: str) -> JobState:
    """Map a state word from ``squeue`` or ``sacct``."""
    word = reported.strip().split()[0].upper() if reported.strip() else ""
    word = word.rstrip("+")
    return _STATES.get(word, JobState.PENDING)


def exit_code(reported: str) -> int | None:
    """Read the process exit code from a ``sacct`` ``ExitCode`` field.

    The field is ``<exit>:<signal>``; a job killed by a signal reports exit 0,
    so the signal wins when it is set.
    """
    text = reported.strip()
    if not text:
        return None
    code, _, signal = text.partition(":")
    try:
        exit_status = int(code)
        signal_status = int(signal) if signal else 0
    except ValueError:
        return None
    return 128 + signal_status if signal_status else exit_status
