/**
 * logger.ts
 *
 * Structured mobile logger that mirrors the backend's logging approach.
 *
 * Features:
 *  - JSON-structured log entries (timestamp, level, event, service, …)
 *  - File persistence via logStorage (expo-file-system) with rotation
 *  - Batched/debounced writes to avoid blocking the JS thread
 *  - Console output in __DEV__ with level-colored prefixes
 *  - Global unhandled-exception capture via ErrorUtils
 *
 * API (compatible with existing api.ts usage):
 *   logger.debug(message, context?)
 *   logger.info(message, context?)
 *   logger.warn(message, context?, error?)
 *   logger.error(message, context?, error?)
 *   logger.critical(message, context?, error?)
 *   logger.readLogs(file?, limit?)   → Promise<LogEntry[]>
 *   logger.clearLogs()
 *   logger.shareLog(file?)
 */

import { appendLog, clearAllLogs, readLogs, shareLogFile, LogEntry, LogLevel, LogFile } from './logStorage';

// ─── Environment detection ─────────────────────────────────────────────────────
const ENV: string = (() => {
  try {
    const base: string = (process.env.EXPO_PUBLIC_API_BASE_URL ?? '');
    if (base.includes('localhost') || base.includes('127.0.0.1') || base === '') return 'development';
    return 'production';
  } catch {
    return 'development';
  }
})();

// ─── Write queue (batched, 500ms debounce) ─────────────────────────────────────
let _queue: LogEntry[] = [];
let _flushTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleFlush() {
  if (_flushTimer) return;
  _flushTimer = setTimeout(async () => {
    _flushTimer = null;
    const batch = _queue.splice(0, _queue.length);
    for (const entry of batch) {
      await appendLog(entry);
    }
  }, 500);
}

function enqueue(entry: LogEntry) {
  _queue.push(entry);
  scheduleFlush();
}

// ─── Core log function ─────────────────────────────────────────────────────────
function _log(
  level: LogLevel,
  message: string,
  context?: Record<string, unknown>,
  error?: Error
) {
  // Convert from (message, context, error) to LogEntry structure
  const entry: LogEntry = {
    timestamp: new Date().toISOString(),
    level,
    event: _toSnakeCase(message),   // e.g. "Login successful" → "login_successful"
    service: 'mobile',
    environment: ENV,
    ...(context ?? {}),
    // Attach error details if provided
    ...(error
      ? {
          error: error.message,
          stack: error.stack?.slice(0, 2000),
        }
      : {}),
  };

  // Dev console output
  if (__DEV__) {
    const prefix = `[${level}] ${message}`;
    const meta = { ...(context ?? {}), ...(error ? { error: error.message } : {}) };
    const hasMeta = Object.keys(meta).length > 0;
    switch (level) {
      case 'DEBUG':
      case 'INFO':
        // eslint-disable-next-line no-console
        hasMeta ? console.log(prefix, meta) : console.log(prefix);
        break;
      case 'WARN':
        // eslint-disable-next-line no-console
        hasMeta ? console.warn(prefix, meta) : console.warn(prefix);
        break;
      case 'ERROR':
      case 'CRITICAL':
        // eslint-disable-next-line no-console
        hasMeta ? console.error(prefix, meta) : console.error(prefix);
        break;
    }
  }

  enqueue(entry);
}

/** Convert "Login successful" → "login_successful" */
function _toSnakeCase(str: string): string {
  return str
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '');
}

// ─── Public logger ─────────────────────────────────────────────────────────────
class Logger {
  debug(message: string, context?: Record<string, unknown>) {
    if (__DEV__) _log('DEBUG', message, context);
  }

  info(message: string, context?: Record<string, unknown>) {
    _log('INFO', message, context);
  }

  warn(message: string, context?: Record<string, unknown>, error?: Error) {
    _log('WARN', message, context, error);
  }

  error(message: string, context?: Record<string, unknown>, error?: Error) {
    _log('ERROR', message, context, error);
  }

  critical(message: string, context?: Record<string, unknown>, error?: Error) {
    _log('CRITICAL', message, context, error);
  }

  /** Read recent log entries from device storage (newest first) */
  readLogs(file?: LogFile, limit?: number): Promise<LogEntry[]> {
    return readLogs(file, limit);
  }

  /** Clear all on-device log files */
  clearLogs(): Promise<void> {
    return clearAllLogs();
  }

  /** Share a log file via native share sheet (requires expo-sharing) */
  async shareLog(file?: LogFile): Promise<void> {
    return shareLogFile(file);
  }
}

export const logger = new Logger();

// ─── Global error capture ──────────────────────────────────────────────────────
let _handlerInstalled = false;

/**
 * Call once at app startup (e.g. in App.tsx or AppNavigator.tsx useEffect).
 * Captures unhandled JS exceptions and writes them to the CRITICAL log.
 */
export function installGlobalErrorHandler(): void {
  if (_handlerInstalled) return;
  _handlerInstalled = true;

  try {
    const prevHandler = ErrorUtils.getGlobalHandler();
    ErrorUtils.setGlobalHandler((error: Error, isFatal?: boolean) => {
      _log('CRITICAL', 'unhandled_exception', {
        fatal: isFatal ?? false,
      }, error);

      // Flush immediately on fatal crash (don't wait for debounce)
      if (isFatal) {
        const batch = _queue.splice(0, _queue.length);
        batch.forEach((e) => appendLog(e));
      }

      prevHandler(error, isFatal);
    });
  } catch {
    // ErrorUtils may not be available in all environments (e.g. tests)
  }
}

// Re-export types for consumers
export type { LogEntry, LogLevel, LogFile };
