import { z } from 'zod/v4'

export const TUNGSTEN_TOOL_NAME = 'tungsten'

export const TungstenTool = {
  name: TUNGSTEN_TOOL_NAME,
  async prompt() {
    return 'Tungsten is not available in this local build.'
  },
  description: 'Unavailable in this local build.',
  inputSchema: z.object({}),
  isEnabled() {
    return false
  },
  async call() {
    throw new Error('Tungsten is not available in this local build.')
  },
}
