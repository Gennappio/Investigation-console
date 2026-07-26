# ADR 0007: Runs on a scheduler are reconciled, not awaited

Date: 2026-07-26
Status: accepted

## Context

Milestone 2's `lab run` submitted a command, waited for the child process, and
collected its outputs in one call. That works because the local backend owns
the process it started.

A cluster job does not work that way. `sbatch` returns as soon as the job is
queued, and the job may start hours later, on another machine, long after the
submitting command has exited. Blocking `lab run` until a queued job finishes
would tie a researcher's terminal to the scheduler's queue, and a lost
connection would leave a run recorded as `running` for ever, with its outputs
never collected.

## Decision

A run has three phases, and the command that starts it need not be the one that
finishes it:

1. `start_run` writes the record, prepares scratch, submits, and stores the
   scheduler's job identifier on the record.
2. `refresh_run` asks the backend what became of that job. If it has ended, the
   same call collects stdout, stderr, outputs and the manifest snapshot into
   permanent storage and closes the record.
3. `execute_run` (start, then poll to the end) remains for backends that finish
   within the command.

`lab run --backend slurm` therefore submits and returns, reporting the run as
queued; `lab status <RUN-id>` reconciles it, which is where a finished job is
collected. `--wait` polls in the foreground when a researcher wants that, and a
local run always waits, because nothing else can adopt its child process.

Two consequences of the state machine (AGENTS.md section 16.3) follow:

- A job seen only after it ended still passes through `running` on its way to a
  terminal state. It did run; the platform simply never observed it, and
  recording the passage keeps the recorded history honest.
- A run that is submitted but unfinished is not a failure: `lab run` exits 0
  and names the command that will collect it.

An unknown job is reported as **pending**, never as finished. SLURM accounting
lags behind submission, and treating a gap in `sacct` as completion would close
a run that is still executing and collect outputs that do not exist yet.

## Alternatives considered

- Blocking until the job finishes: rejected, it makes a researcher's terminal a
  dependency of a queue that may be hours deep.
- A background daemon polling the cluster: rejected for this milestone. It adds
  a process to run, supervise and secure, for a platform that so far has none.
  `lab status` gives the same reconciliation at the moment someone asks.
- Collecting from the job script itself: rejected, a job that is cancelled or
  killed never reaches its own epilogue, so runs would silently lose outputs
  exactly when something went wrong.

## Consequences

Outputs of a cluster run reach permanent storage the first time anyone asks
about the run. A run nobody asks about stays `queued` or `running` in the
record even though the cluster has finished it, which is visible and
correctable rather than wrong. `lab report` still refuses to write a report for
a run that has not reached a terminal state.

The job index (`$LAB_HOME/slurm/<job id>.json`) is what makes reconciliation
possible from a later process; a run submitted under one `LAB_HOME` cannot be
collected from another, and says so.

## Migration implications

The polling daemon or webhook of a later milestone replaces how `refresh_run`
is triggered, not what it does. The API of Milestone 6 exposes the same call as
`GET /runs/{id}/status`.
