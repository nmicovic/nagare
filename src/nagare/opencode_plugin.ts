/**
 * nagare state writer plugin for OpenCode.
 *
 * Writes session state files to ~/.local/share/nagare/states/ so that
 * nagare's picker and notification system can monitor OpenCode sessions
 * the same way it monitors Claude Code sessions.
 *
 * Install: copy this file to ~/.config/opencode/plugin/nagare.ts
 * Or run: nagare setup
 */

import { mkdirSync } from "fs"
import { join } from "path"
import { createHash } from "crypto"

const STATE_DIR = join(Bun.env.HOME!, ".local", "share", "nagare", "states")

function stableId(cwd: string): string {
  // Generate a stable session ID from the project path so nagare can
  // track the same opencode session across restarts.
  return "oc-" + createHash("md5").update(cwd).digest("hex").slice(0, 12)
}

function writeState(
  sessionId: string,
  cwd: string,
  state: string,
  eventName: string,
  notificationType: string = "",
  lastMessage: string = "",
) {
  const data = {
    state,
    session_id: sessionId,
    cwd,
    event: eventName,
    notification_type: notificationType,
    last_message: lastMessage,
    timestamp: new Date().toISOString(),
  }
  Bun.write(join(STATE_DIR, `${sessionId}.json`), JSON.stringify(data))
}

function eventToState(eventType: string): string | null {
  switch (eventType) {
    case "session.created":
      return "idle"
    case "session.idle":
      return "idle"
    case "session.deleted":
      return "dead"
    case "session.error":
      return "idle"
    case "tool.execute.before":
      return "working"
    case "tool.execute.after":
      return null // Don't update — wait for session.idle
    case "permission.asked":
      return "waiting_input"
    case "permission.updated":
      return "working"
    case "message.updated":
      return "working"
    default:
      return null
  }
}

export default async ({ directory }: { directory: string }) => {
  mkdirSync(STATE_DIR, { recursive: true })

  return {
    event: async ({ event }: { event: any }) => {
      try {
        const state = eventToState(event.type)
        if (state === null) return

        const cwd = event.projectPath || directory
        const sessionId = event.sessionId || stableId(cwd)

        let notificationType = ""
        if (event.type === "permission.asked") {
          notificationType = "permission_prompt"
        }

        writeState(sessionId, cwd, state, event.type, notificationType)
      } catch {
        // Never crash OpenCode
      }
    },
  }
}
