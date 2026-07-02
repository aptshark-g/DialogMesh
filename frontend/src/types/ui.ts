export interface ConnectionState {
  status: 'connecting' | 'open' | 'closing' | 'closed' | 'error';
  latencyMs: number | null;
  lastError: string | null;
}
