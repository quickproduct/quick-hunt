/**
 * logStorage.ts
 *
 * Low-level file I/O for the mobile logging system.
 * Mirrors the backend's structured logging approach (JSON lines, rotating files).
 *
 * Log files (in DocumentDirectory/logs/):
 *   app.log      — all levels, one JSON line per entry
 *   error.log    — ERROR + CRITICAL only
 *   critical.log — CRITICAL only
 *
 * Rotation: if a file exceeds MAX_FILE_BYTES, trim to the last KEEP_LINES lines.
 */

// Use the legacy expo-file-system API (documentDirectory, readAsStringAsync, etc.)
import * as FileSystem from 'expo-file-system/legacy';

// ─── Config ────────────────────────────────────────────────────────────────────
const LOG_DIR = `${FileSystem.documentDirectory ?? ''}logs/`;
const MAX_FILE_BYTES = 200 * 1024; // 200 KB
const KEEP_LINES = 150;

// ─── Types ─────────────────────────────────────────────────────────────────────
export type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'CRITICAL';
export type LogFile = 'app' | 'error' | 'critical';

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  event: string;
  service: 'mobile';
  environment: string;
  screen?: string;
  user_id?: string;
  job_id?: string;
  candidate_id?: string;
  task_id?: string;
  url?: string;
  method?: string;
  status_code?: number;
  duration_ms?: number;
  error?: string;
  stack?: string;
  fatal?: boolean;
  [key: string]: unknown;
}

// ─── Helpers ───────────────────────────────────────────────────────────────────
function filePath(file: LogFile): string {
  return `${LOG_DIR}${file}.log`;
}

async function ensureDir(): Promise<void> {
  const info = await FileSystem.getInfoAsync(LOG_DIR);
  if (!info.exists) {
    await FileSystem.makeDirectoryAsync(LOG_DIR, { intermediates: true });
  }
}

async function readFileContent(path: string): Promise<string> {
  try {
    const info = await FileSystem.getInfoAsync(path);
    if (!info.exists) return '';
    return await FileSystem.readAsStringAsync(path);
  } catch {
    return '';
  }
}

async function maybeRotate(path: string): Promise<void> {
  try {
    const info = await FileSystem.getInfoAsync(path);
    if (!info.exists) return;
    const size = (info as any).size ?? 0;
    if (size < MAX_FILE_BYTES) return;

    const content = await FileSystem.readAsStringAsync(path);
    const lines = content.split('\n').filter((l) => l.trim().length > 0);
    const trimmed = lines.slice(-KEEP_LINES).join('\n') + '\n';
    await FileSystem.writeAsStringAsync(path, trimmed);
  } catch {
    // Rotation failures are non-fatal — ignore silently
  }
}

// ─── Public API ────────────────────────────────────────────────────────────────

/**
 * Append a single log entry as a JSON line to the appropriate files.
 * Automatically routes to error.log / critical.log for higher severity.
 * Uses read+concat+write since the legacy FS API has no native append mode.
 */
export async function appendLog(entry: LogEntry): Promise<void> {
  try {
    await ensureDir();
    const line = JSON.stringify(entry) + '\n';

    // Always write to app.log
    const appPath = filePath('app');
    const appContent = await readFileContent(appPath);
    await FileSystem.writeAsStringAsync(appPath, appContent + line);

    // ERROR → also write to error.log
    if (entry.level === 'ERROR' || entry.level === 'CRITICAL') {
      const errPath = filePath('error');
      const errContent = await readFileContent(errPath);
      await FileSystem.writeAsStringAsync(errPath, errContent + line);
    }

    // CRITICAL → also write to critical.log
    if (entry.level === 'CRITICAL') {
      const critPath = filePath('critical');
      const critContent = await readFileContent(critPath);
      await FileSystem.writeAsStringAsync(critPath, critContent + line);
    }

    // Fire-and-forget rotation (non-blocking)
    void maybeRotate(appPath);
  } catch {
    // File writes must NEVER crash the app
  }
}

/**
 * Read the last `limit` entries from a log file.
 * Returns parsed LogEntry objects; unparseable lines stored as _raw.
 */
export async function readLogs(file: LogFile = 'app', limit = 100): Promise<LogEntry[]> {
  try {
    await ensureDir();
    const path = filePath(file);
    const info = await FileSystem.getInfoAsync(path);
    if (!info.exists) return [];

    const content = await FileSystem.readAsStringAsync(path);
    const lines = content.split('\n').filter((l) => l.trim().length > 0);
    const recent = lines.slice(-limit);

    return recent.map((line) => {
      try {
        return JSON.parse(line) as LogEntry;
      } catch {
        return {
          timestamp: '',
          level: 'INFO' as LogLevel,
          event: line,
          service: 'mobile' as const,
          environment: '',
          _raw: line,
        };
      }
    }).reverse(); // newest first
  } catch {
    return [];
  }
}

/** Clear all log files */
export async function clearAllLogs(): Promise<void> {
  try {
    const files: LogFile[] = ['app', 'error', 'critical'];
    await Promise.all(files.map((f) => FileSystem.deleteAsync(filePath(f), { idempotent: true })));
  } catch {
    // ignore
  }
}

/** Returns the URI for a log file (used by expo-sharing) */
export function getLogFileUri(file: LogFile): string {
  return filePath(file);
}

/** Share a log file via the native share sheet (requires expo-sharing) */
export async function shareLogFile(file: LogFile = 'app'): Promise<void> {
  try {
    await ensureDir();
    const uri = getLogFileUri(file);
    const info = await FileSystem.getInfoAsync(uri);
    if (!info.exists) {
      throw new Error('No log file found');
    }
    const Sharing = await import('expo-sharing');
    const available = await Sharing.isAvailableAsync();
    if (!available) {
      throw new Error('Sharing not available on this device');
    }
    await Sharing.shareAsync(uri, {
      mimeType: 'text/plain',
      dialogTitle: `${file}.log`,
      UTI: 'public.plain-text',
    });
  } catch (err: any) {
    throw new Error(err?.message ?? 'Failed to share log file');
  }
}
