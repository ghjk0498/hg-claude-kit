export type Reading = { tokens: number }

declare module 'claude-code' {
  interface PluginState {
    'context-meter': { last: Reading | null }
  }
}
