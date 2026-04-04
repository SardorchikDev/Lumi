export type ConnectorTextDelta = {
  type?: string
  text?: string
}

export type ConnectorTextBlock = {
  type?: string
  text?: string
}

export function isConnectorTextBlock(
  value: unknown,
): value is ConnectorTextBlock {
  if (!value || typeof value !== 'object') return false
  const block = value as { type?: unknown }
  return block.type === 'connector_text'
}
