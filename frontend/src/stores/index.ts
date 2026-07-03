// FILE: src/stores/index.ts

export {
  useSessionStore,
  useSessionId,
  useWsConnected,
  useSessionState,
  useMessages,
  useIsLoading,
  useStoreError,
  usePendingClarification,
  useCognitiveProfile,
  useFsm,
  useCapabilities,
  useRestBaseUrl,
  useTaskGraph,
  useLatestMessage,
  useUserMessages,
  useAssistantMessages,
  useMessageCount,
  useHasActiveSession,
  useSessionExpiresIn,
} from './sessionStore';

export {
  useThemeStore,
  useTheme,
  useToggleTheme,
  useSetTheme,
} from './themeStore';

export {
  useGraphStore,
  useGraphNodes,
  useGraphEdges,
  useGraphSelectedNodeId,
  useGraphViewMode,
  useGraphFilters,
  useGraphSearchQuery,
} from './graphStore';

export {
  useTaskStore,
  useTaskGraphStore,
  useTaskExecutionStatus,
  useTaskSelectedNodeId,
} from './taskStore';

export {
  useProfileStore,
  useProfiles,
  useSelectedProfile,
  useProfileLoading,
  useProfileError,
  useAggregatedStats,
  useIntentDistribution,
  useRadarData,
} from './profileStore';

export {
  useAnalyticsStore,
  useTrendData,
  useAnalyticsIntentDistribution,
  useAnalyticsWordCloud,
  useAnalyticsLastUpdated,
  useAnalyticsComputing,
  useGlobalAnalytics,
} from './analyticsStore';

export type { ProfileStore } from './profileStore';
export type { SessionStore } from '../types/api';
export type { SessionBaseState as SessionState } from '../types/api';
export type { SessionActions } from '../types/api';
export type { Theme } from './themeStore';

export {
  useOverlayStore,
  useOverlayOpen,
  useOverlayMinimized,
  useOverlayPosition,
  useOverlayUnreadCount,
  useOverlayBadgeVisible,
} from './overlayStore';
export type { OverlayState, OverlayActions } from './overlayStore';

export {
  useUIStore,
  useSidePanelOpen,
  useSidePanelTitle,
  useSidePanelWidth,
} from './uiStore';
export type { UIStore } from './uiStore';
