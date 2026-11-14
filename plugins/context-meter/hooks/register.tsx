import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Reading } from '../types'

// away_check.py의 손익분기(Opus 5.5, 바닥값 약 75K 기준 약 120~129K)
export const BREAK_EVEN = 125_000

const last = atom({ plugin: 'context-meter', key: 'last' } as const, null)

const k = (n: number) => `${Math.round(n / 1000)}K`

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const r = await next(e)
    const { context } = await $.session.usage()
    if (context.tokens !== undefined) {
      const reading: Reading = { tokens: context.tokens }
      await update($, last, () => reading)
    }
    return r
  })

  on('turn.complete', async ($, e, next) => {
    const r = await next(e)
    const { context } = await $.session.usage()
    if (context.tokens !== undefined) {
      const reading: Reading = { tokens: context.tokens }
      await update($, last, () => reading)
    }
    return r
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const reading = await read($, last)
    if (e.props.hasSurvey || reading === null || reading.tokens < BREAK_EVEN) {
      return next(e)
    }
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box>
        <Text color="warning">컨텍스트 {k(reading.tokens)} · 손익분기 {k(BREAK_EVEN)} 넘음</Text>
        <Text dimColor> — 1시간 넘게 비울 때: 이어갈 일이면 /compact, 다른 일이면 새 세션</Text>
      </Box>
    )
  })
}
