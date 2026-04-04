import { mkdirSync } from 'fs'
import { join } from 'path'

process.env.USER_TYPE ??= 'external'
process.env.CLAUDE_CODE_ENTRYPOINT ??= 'cli'
process.env.DISABLE_AUTOUPDATER ??= '1'
process.env.CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL ??= '1'
process.env.CLAUDE_CONFIG_DIR ??= join(process.cwd(), '.local-agent')

mkdirSync(process.env.CLAUDE_CONFIG_DIR, { recursive: true })

const macroDefaults = {
  VERSION: '999.0.0-local',
  VERSION_CHANGELOG: '',
  BUILD_TIME: new Date().toISOString(),
  PACKAGE_URL: '@anthropic-ai/claude-code',
  NATIVE_PACKAGE_URL: '@anthropic-ai/claude-code',
  FEEDBACK_CHANNEL: 'https://github.com/anthropics/claude-code/issues',
  ISSUES_EXPLAINER: 'run /bug or file an issue on GitHub',
}

if (!globalThis.MACRO) {
  globalThis.MACRO = macroDefaults
} else {
  globalThis.MACRO = {
    ...macroDefaults,
    ...globalThis.MACRO,
  }
}
