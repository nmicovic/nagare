### Context Document for AI Assistant: Project `nagare`

**Project Name:** `nagare` (Japanese for "flow" / 流れ)
**Project Type:** CLI Tool / Workspace Manager
**Core Dependencies:** `tmux`, `ccode`, Unix shell

#### 1. The Core Problem

I use `ccode` extensively and constantly switch between multiple `tmux` sessions. Currently, this workflow requires manual context switching, checking if background jobs (like builds, searches, or tests) are done, and remembering which session holds which context. It breaks the "flow" state.

#### 2. What `nagare` Does (The Solution)

`nagare` is a unified CLI tool designed to manage `tmux` sessions and `ccode` instances. Its primary goal is to eliminate friction by doing two things:

1. **Frictionless Context Switching:** Providing fast, intuitive commands to jump between active development environments.
2. **Intelligent Monitoring & Notification:** Running in the background to monitor the state of `ccode` and other processes within `tmux` sessions. It actively alerts the user *when* a specific session requires attention (e.g., a long-running process finished, a build failed, or a task completed), acting as an intelligent guide.

#### 3. Key Features & Requirements

* **Session Management:** Create, list, and attach to `tmux` sessions seamlessly. When a session is created, it should automatically initialize the `ccode` environment for that specific workspace.
* **State Polling/Monitoring:** A daemon or background process that checks the status of running jobs inside detached `tmux` sessions.
* **Notification System:** A way to alert the user that a different session needs attention. (This could be via OS-level notifications, terminal bells, or injecting a status indicator into the active `tmux` status bar).
* **Smart Jump:** A command that instantly teleports the user to the session that currently requires the most urgent attention based on the monitoring data.

#### 4. Proposed CLI Interface (Draft)

The AI should use these commands as a starting point for building the CLI parser:

* `nagare init <project>`: Bootstraps a new tmux session named `<project>` and starts `ccode` in it.
* `nagare ls`: Lists all active sessions, highlighting which ones are idle, running processes, or require attention.
* `nagare go <project>`: Fast switch to the specified project.
* `nagare next`: Automatically switches to the session that triggered an alert/notification.
* `nagare daemon`: Starts the background monitoring process.

#### 5. Technical Implementation Goals

* The tool should be fast and lightweight (preferred languages: Go, Rust, or a highly optimized Bash/Python script).
* It must interface cleanly with the `tmux` socket/command line to read window states and pane outputs.
* It should parse `ccode` outputs or exit codes to determine process states.
