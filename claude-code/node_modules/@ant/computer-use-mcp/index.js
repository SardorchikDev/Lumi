export const DEFAULT_GRANT_FLAGS = {}
export const API_RESIZE_PARAMS = {}

export function targetImageSize() {
  return { width: 0, height: 0 }
}

export function buildComputerUseTools() {
  return []
}

export function createComputerUseMcpServer() {
  return {
    connect() {
      throw new Error('Computer Use MCP is not available in this local build.')
    },
    setRequestHandler() {},
  }
}

export function bindSessionContext() {
  return async function callComputerUseTool() {
    return {
      isError: true,
      content: [
        {
          type: 'text',
          text: 'Computer use is not available in this local build.',
        },
      ],
    }
  }
}
