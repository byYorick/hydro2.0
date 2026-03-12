import { computed } from 'vue'
import { usePage } from '@inertiajs/vue3'
import type { UserRole } from '@/types/User'

/**
 * Composable для работы с ролями пользователей
 * Централизованная логика проверки прав доступа
 */
export function useRole() {
  const page = usePage()
  const user = computed(() => page.props.auth?.user as { role?: UserRole } | undefined)
  
  const role = computed(() => user.value?.role as UserRole | undefined)
  
  // Проверки конкретных ролей
  const isAgronomist = computed(() => role.value === 'agronomist')
  const isAdmin = computed(() => role.value === 'admin')
  const isEngineer = computed(() => role.value === 'engineer')
  const isOperator = computed(() => role.value === 'operator')
  const isViewer = computed(() => role.value === 'viewer')
  
  // Проверки прав доступа
  const canEdit = computed(() => 
    isAdmin.value || isAgronomist.value || isEngineer.value || isOperator.value
  )
  
  const canManageUsers = computed(() => isAdmin.value)
  
  const canManageSystem = computed(() => isAdmin.value)
  
  const canDiagnose = computed(() => isEngineer.value || isAdmin.value)
  
  const canCreateCommands = computed(() => 
    isAdmin.value || isAgronomist.value || isEngineer.value || isOperator.value
  )
  
  const canEditRecipes = computed(() => 
    isAdmin.value || isAgronomist.value || isOperator.value
  )
  
  const canResolveAlerts = computed(() => 
    isAdmin.value || isAgronomist.value || isEngineer.value || isOperator.value
  )
  
  const canViewOnly = computed(() => isViewer.value)
  
  // Проверка конкретной роли
  const hasRole = (roles: UserRole | UserRole[]): boolean => {
    if (!role.value) return false
    const rolesArray = Array.isArray(roles) ? roles : [roles]
    return rolesArray.includes(role.value)
  }
  
  // Проверка любой из ролей
  const hasAnyRole = (roles: UserRole[]): boolean => {
    if (!role.value) return false
    return roles.includes(role.value)
  }
  
  return {
    // Роль пользователя
    role,
    user,
    
    // Проверки ролей
    isAgronomist,
    isAdmin,
    isEngineer,
    isOperator,
    isViewer,
    
    // Проверки прав
    canEdit,
    canManageUsers,
    canManageSystem,
    canDiagnose,
    canCreateCommands,
    canEditRecipes,
    canResolveAlerts,
    canViewOnly,
    
    // Утилиты
    hasRole,
    hasAnyRole,
  }
}

