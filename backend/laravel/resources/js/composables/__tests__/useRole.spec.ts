import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useRole } from '../useRole'
import type { UserRole } from '@/types/User'

// Mock usePage from Inertia
const mockPage = vi.fn()
vi.mock('@inertiajs/vue3', () => ({
  usePage: () => mockPage(),
}))

describe('useRole', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('role detection', () => {
    it('should detect agronomist role', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {
            user: { role: 'agronomist' as UserRole }
          }
        }
      })

      const { role, isAgronomist } = useRole()
      
      expect(role.value).toBe('agronomist')
      expect(isAgronomist.value).toBe(true)
    })

    it('should detect admin role', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {
            user: { role: 'admin' as UserRole }
          }
        }
      })

      const { role, isAdmin } = useRole()
      
      expect(role.value).toBe('admin')
      expect(isAdmin.value).toBe(true)
    })

    it('should detect engineer role', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {
            user: { role: 'engineer' as UserRole }
          }
        }
      })

      const { role, isEngineer } = useRole()
      
      expect(role.value).toBe('engineer')
      expect(isEngineer.value).toBe(true)
    })

    it('should detect operator role', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {
            user: { role: 'operator' as UserRole }
          }
        }
      })

      const { role, isOperator } = useRole()
      
      expect(role.value).toBe('operator')
      expect(isOperator.value).toBe(true)
    })

    it('should detect viewer role', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {
            user: { role: 'viewer' as UserRole }
          }
        }
      })

      const { role, isViewer } = useRole()
      
      expect(role.value).toBe('viewer')
      expect(isViewer.value).toBe(true)
    })

    it('should handle undefined user', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {}
        }
      })

      const { role, isViewer, isAdmin } = useRole()
      
      expect(role.value).toBeUndefined()
      expect(isViewer.value).toBe(false)
      expect(isAdmin.value).toBe(false)
    })
  })

  describe('permissions', () => {
    it('should allow edit for admin, agronomist, engineer, operator', () => {
      const roles: UserRole[] = ['admin', 'agronomist', 'engineer', 'operator']
      
      roles.forEach(role => {
        mockPage.mockReturnValue({
          props: {
            auth: {
              user: { role }
            }
          }
        })

        const { canEdit } = useRole()
        expect(canEdit.value).toBe(true)
      })
    })

    it('should not allow edit for viewer', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {
            user: { role: 'viewer' as UserRole }
          }
        }
      })

      const { canEdit } = useRole()
      expect(canEdit.value).toBe(false)
    })

    it('should allow user management only for admin', () => {
      const roles: UserRole[] = ['admin', 'agronomist', 'engineer', 'operator', 'viewer']
      
      roles.forEach(role => {
        mockPage.mockReturnValue({
          props: {
            auth: {
              user: { role }
            }
          }
        })

        const { canManageUsers } = useRole()
        expect(canManageUsers.value).toBe(role === 'admin')
      })
    })

    it('should allow system management only for admin', () => {
      const roles: UserRole[] = ['admin', 'agronomist', 'engineer', 'operator', 'viewer']
      
      roles.forEach(role => {
        mockPage.mockReturnValue({
          props: {
            auth: {
              user: { role }
            }
          }
        })

        const { canManageSystem } = useRole()
        expect(canManageSystem.value).toBe(role === 'admin')
      })
    })

    it('should allow diagnosis for engineer and admin', () => {
      const roles: UserRole[] = ['admin', 'engineer', 'agronomist', 'operator', 'viewer']
      
      roles.forEach(role => {
        mockPage.mockReturnValue({
          props: {
            auth: {
              user: { role }
            }
          }
        })

        const { canDiagnose } = useRole()
        expect(canDiagnose.value).toBe(role === 'admin' || role === 'engineer')
      })
    })

    it('should allow command creation for admin, agronomist, engineer, operator', () => {
      const roles: UserRole[] = ['admin', 'agronomist', 'engineer', 'operator', 'viewer']
      
      roles.forEach(role => {
        mockPage.mockReturnValue({
          props: {
            auth: {
              user: { role }
            }
          }
        })

        const { canCreateCommands } = useRole()
        expect(canCreateCommands.value).toBe(role !== 'viewer')
      })
    })

    it('should allow recipe editing for admin, agronomist, operator', () => {
      const roles: UserRole[] = ['admin', 'agronomist', 'operator', 'engineer', 'viewer']
      
      roles.forEach(role => {
        mockPage.mockReturnValue({
          props: {
            auth: {
              user: { role }
            }
          }
        })

        const { canEditRecipes } = useRole()
        expect(canEditRecipes.value).toBe(
          role === 'admin' || role === 'agronomist' || role === 'operator'
        )
      })
    })

    it('should allow alert resolution for admin, agronomist, engineer, operator', () => {
      const roles: UserRole[] = ['admin', 'agronomist', 'engineer', 'operator', 'viewer']
      
      roles.forEach(role => {
        mockPage.mockReturnValue({
          props: {
            auth: {
              user: { role }
            }
          }
        })

        const { canResolveAlerts } = useRole()
        expect(canResolveAlerts.value).toBe(role !== 'viewer')
      })
    })

    it('should identify view-only mode for viewer', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {
            user: { role: 'viewer' as UserRole }
          }
        }
      })

      const { canViewOnly } = useRole()
      expect(canViewOnly.value).toBe(true)
    })
  })

  describe('utility functions', () => {
    it('should check hasRole for single role', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {
            user: { role: 'admin' as UserRole }
          }
        }
      })

      const { hasRole } = useRole()
      
      expect(hasRole('admin')).toBe(true)
      expect(hasRole('viewer')).toBe(false)
    })

    it('should check hasRole for multiple roles', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {
            user: { role: 'admin' as UserRole }
          }
        }
      })

      const { hasRole } = useRole()
      
      expect(hasRole(['admin', 'viewer'])).toBe(true)
      expect(hasRole(['viewer', 'operator'])).toBe(false)
    })

    it('should check hasAnyRole', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {
            user: { role: 'admin' as UserRole }
          }
        }
      })

      const { hasAnyRole } = useRole()
      
      expect(hasAnyRole(['admin', 'viewer'])).toBe(true)
      expect(hasAnyRole(['viewer', 'operator'])).toBe(false)
    })

    it('should return false for hasRole when user is undefined', () => {
      mockPage.mockReturnValue({
        props: {
          auth: {}
        }
      })

      const { hasRole } = useRole()
      
      expect(hasRole('admin')).toBe(false)
      expect(hasRole(['admin', 'viewer'])).toBe(false)
    })
  })
})

