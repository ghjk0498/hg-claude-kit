import { expect, test } from 'claude-code/testing'

const BAND = {
  plugin: 'context-meter',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isCollapsed: false,
    isWorking: false,
    maxRows: 10,
    bodyColumns: 80,
    scroll: { offset: 0, bodyRows: 10 },
    view: {},
  },
} as const

const usage = (tokens: number) => ({
  value: { startedAt: 0, context: { tokens, window: 1_000_000 }, rateLimits: [] },
})

test('over the break-even the band warns, on terminal and desktop', async ($, on) => {
  on('session.usage', () => usage(312_000))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...BAND, surface })
    const t = await ui.find({ type: 'Text', text: /손익분기/ })
    expect(t?.text).toBe('컨텍스트 312K · 손익분기 125K 넘음')
    const hint = await ui.find({ type: 'Text', text: /\/away/ })
    expect(hint?.text).toBe(' — 1시간+ 비울 때: 이어감 /compact · 다른 일 새 세션 · 맡기고 감 /away')
    await ui.unmount()
  }
})

test('under the break-even the band stays empty', async ($, on) => {
  on('session.usage', () => usage(90_000))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('ui.render', ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine</Text>
  })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  const ui = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /손익분기/ })).toBeUndefined()
  await ui.unmount()
})
