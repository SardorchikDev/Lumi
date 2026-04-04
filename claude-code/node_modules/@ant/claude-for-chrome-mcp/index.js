export const BROWSER_TOOLS = []

export function createClaudeForChromeMcpServer() {
  return {
    connect() {
      throw new Error('Claude in Chrome is not available in this local build.')
    },
    setRequestHandler() {},
  }
}
