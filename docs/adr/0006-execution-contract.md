# ADR 0006: The execution contract between the platform and a repository

Date: 2026-07-26
Status: accepted

## Context

`lab run` executes a command that the repository declares in `lab.yaml`. The
platform must tell that command where to write, which configuration to read and
which run it belongs to, without a shell (AGENTS.md sections 15.3 and 16.1),
without leaking cluster paths into manifests (section 2.4), and in an isolated
working directory (section 8.1).

The manifest example in AGENTS.md section 7.1 already assumes a variable:
`"${LAB_EXPERIMENT_CONFIG}"`.

## Decision

A run executes with these environment variables:

| Variable | Meaning |
|---|---|
| `LAB_RUN_ID` | Identifier of this run |
| `LAB_EXPERIMENT_ID` | Experiment being executed |
| `LAB_EXPERIMENT_CONFIG` | Path of the generated configuration file |
| `LAB_OUTPUT_DIR` | Directory to write outputs into |
| `LAB_PROJECT_DIR` | Repository root, read-only during the run |
| `PYTHONPATH` | `<project>/src`, so the repository's package imports |

Rules that follow from it:

1. **Placeholders are expanded by the platform, not by a shell.** `${NAME}` in
   an argument of a command profile is substituted from the table above and the
   result is executed as an argument list. An unknown name is left untouched
   rather than replaced by an empty string, because silently emptying an
   argument changes what runs without saying so.
2. **The working directory is scratch, not the repository.** Each run gets
   `LAB_HOME/work/<RUN-id>/`, holding the generated `config.yaml`, the manifest
   snapshot, `logs/`, and the output directory the manifest declares. Outputs
   are collected from there into permanent artifact storage, and the run is
   marked completed only afterwards (section 8.3).
3. **The configuration file is flat.** Keys are the experiment's parameters
   plus `run_id`, `experiment_id`, `seed` (the first seed) and `seeds`. Values
   are JSON, which is valid YAML, so a repository can parse it with a YAML
   library or trivially by hand.
4. **Metrics are reported in `metrics.json`.** If the output directory contains
   one, its contents appear in the report as the run's main metrics. Anything
   else the run writes is still collected and checksummed as an artifact.
5. **Inside a container** the same variables point at container paths: the
   repository is mounted read-only at `/workspace` and the scratch directory is
   the working directory at `/scratch`.

## Alternatives considered

- Executing in the repository root: rejected, outputs would accumulate in the
  working copy and two runs would overwrite each other, so a run could not be
  reproduced from its record.
- Passing parameters as command-line arguments: rejected, it forces every
  repository to accept a platform-specific argument grammar; a configuration
  file keeps the interface to one path.
- Expanding placeholders with a shell: rejected outright. It would make manifest
  content executable, which section 15.3 forbids.

## Consequences

A repository is portable: it reads one configuration path and writes to one
output directory, and the same manifest runs locally, in a container, and later
through SLURM. A command that hardcodes relative paths into the repository
(`configs/smoke.yaml`) works under `lab test`, which runs in the repository, but
not under `lab run`, which does not; such commands must use
`LAB_EXPERIMENT_CONFIG` or `LAB_PROJECT_DIR`.

## Migration implications

The SLURM backend of Milestone 3 renders the same variables into the generated
`sbatch` script, with scratch on the cluster filesystem. Repositories written
against this contract do not change.
