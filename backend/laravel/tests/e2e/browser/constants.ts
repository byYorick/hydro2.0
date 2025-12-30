// Константы для data-testid значений
export const TEST_IDS = {
  // Login
  LOGIN_FORM: 'login-form',
  LOGIN_EMAIL: 'login-email',
  LOGIN_PASSWORD: 'login-password',
  LOGIN_SUBMIT: 'login-submit',
  LOGIN_ERROR: 'login-error',

  // Dashboard
  DASHBOARD_ZONES_COUNT: 'dashboard-zones-count',
  DASHBOARD_ZONE_CARD: (id: number) => `zone-card-${id}`,
  DASHBOARD_ALERTS_COUNT: 'dashboard-alerts-count',
  DASHBOARD_EVENTS_PANEL: 'dashboard-events-panel',
  DASHBOARD_EVENT_FILTER: (kind: string) => `dashboard-event-filter-${kind}`,

  // Zone
  ZONE_STATUS_BADGE: 'zone-status-badge',
  ZONE_START_BTN: 'zone-start-btn',
  ZONE_PAUSE_BTN: 'zone-pause-btn',
  ZONE_RESUME_BTN: 'zone-resume-btn',
  ZONE_HARVEST_BTN: 'zone-harvest-btn',
  ZONE_COMMAND_FORM: 'zone-command-form',
  ZONE_COMMAND_SUBMIT: 'zone-command-submit',
  ZONE_EVENTS_LIST: 'zone-events-list',
  ZONE_SNAPSHOT_LOADED: 'zone-snapshot-loaded',
  ZONE_CARD: (id: number) => `zone-card-${id}`,
  ZONE_CARD_STATUS: 'zone-card-status',
  ZONE_CARD_LINK: 'zone-card-link',

  // Alerts
  ALERTS_FILTER_ACTIVE: 'alerts-filter-active',
  ALERTS_FILTER_ZONE: 'alerts-filter-zone',
  ALERTS_TABLE: 'alerts-table',
  ALERT_ROW: (id: number) => `alert-row-${id}`,
  ALERT_RESOLVE_BTN: (id: number) => `alert-resolve-btn-${id}`,

  // Analytics
  ANALYTICS_FILTER_ZONE: 'analytics-filter-zone',
  ANALYTICS_FILTER_METRIC: 'analytics-filter-metric',
  ANALYTICS_FILTER_PERIOD: 'analytics-filter-period',
  ANALYTICS_CHART: 'analytics-telemetry-chart',

  // Devices
  DEVICES_FILTER_TYPE: 'devices-filter-type',
  DEVICES_FILTER_QUERY: 'devices-filter-query',
  DEVICES_FILTER_FAVORITES: 'devices-filter-favorites',

  // Zones
  ZONES_FILTER_STATUS: 'zones-filter-status',
  ZONES_FILTER_QUERY: 'zones-filter-query',
  ZONES_FILTER_FAVORITES: 'zones-filter-favorites',

  // Toast
  TOAST: (variant: string) => `toast-${variant}`,
  TOAST_MESSAGE: 'toast-message',

  // Recipe
  RECIPE_NAME_INPUT: 'recipe-name-input',
  RECIPE_DESCRIPTION_INPUT: 'recipe-description-input',
  RECIPE_ATTACH_BTN: 'recipe-attach-btn',
  CYCLE_PHASE: (index: number) => `cycle-phase-${index}`,

  // Bindings
  BINDING_ROLE_SELECT: (nodeId: number, channelId: number) => `binding-role-select-${nodeId}-${channelId}`,
  BINDING_SUBMIT: 'binding-submit',

  // WebSocket
  WS_STATUS_INDICATOR: 'ws-status-indicator',
  WS_STATUS_CONNECTED: 'ws-status-connected',
  WS_STATUS_DISCONNECTED: 'ws-status-disconnected',
} as const;

// Константы для тестовых данных
export const TEST_DATA = {
  GREENHOUSE_NAME: (timestamp: number) => `Test Greenhouse ${timestamp}`,
  ZONE_NAME: (timestamp: number) => `Test Zone ${timestamp}`,
  RECIPE_NAME: (timestamp: number) => `Test Recipe ${timestamp}`,
  RECIPE_DESCRIPTION: 'Test recipe description for e2e tests',
} as const;
