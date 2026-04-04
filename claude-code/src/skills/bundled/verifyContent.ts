// The original source bundle inlines markdown assets here. This extracted
// tree does not include those files, so keep a compact fallback instead.

export const SKILL_MD: string = `# verify

Use this skill when the user asks you to verify code changes by running the
smallest relevant checks and reporting what passed, failed, or could not run.`

export const SKILL_FILES: Record<string, string> = {
  'examples/cli.md': 'Run targeted verification commands and report the result.',
  'examples/server.md':
    'Prefer the smallest server-side verification step that covers the change.',
}
