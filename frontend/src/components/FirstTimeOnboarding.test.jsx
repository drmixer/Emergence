import { describe, expect, it } from 'vitest'
import { shouldAutoOpenOnboarding } from './FirstTimeOnboarding'

describe('FirstTimeOnboarding', () => {
    it('auto-opens only on main entry surfaces', () => {
        expect(shouldAutoOpenOnboarding('/')).toBe(true)
        expect(shouldAutoOpenOnboarding('/dashboard')).toBe(true)
        expect(shouldAutoOpenOnboarding('/calendar')).toBe(false)
        expect(shouldAutoOpenOnboarding('/archive')).toBe(false)
        expect(shouldAutoOpenOnboarding('/runs/real-20260517t220144z/replay')).toBe(false)
        expect(shouldAutoOpenOnboarding('/runs/real-20260517t220144z/reports/story')).toBe(false)
        expect(shouldAutoOpenOnboarding('/glossary')).toBe(false)
    })
})
