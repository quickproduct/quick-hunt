# Mobile App Logs

This directory contains structured log files for the mobile application.

## Log Levels

- info.log - General application information
- warn.log - Warnings and non-critical issues
- error.log - Errors and exceptions
- critical.log - Critical failures requiring immediate attention

## Development Workflow

### Real-time Logging (Development)

To get real-time logs written to this directory during development:

1. Start the dev log server in a separate terminal:
   ```bash
   npm run dev-log-server
   ```

2. Start the Expo dev server in another terminal:
   ```bash
   npm start
   ```

3. Run the app on simulator/emulator. All logs will be written to `mobile/logs/` in real-time.

### Production Log Retrieval

For production builds or when the dev log server is not running:

1. Build and run the app on device/emulator
2. Pull logs from the device:
   ```bash
   npm run pull-logs
   ```

This script automatically detects Android (adb) or iOS (simulator) and pulls the log files.

## How It Works

- **Development**: Logger sends logs via HTTP to dev log server on port 19001, which writes to project directory
- **Production**: Logger writes to device storage using expo-file-system; pull-logs script retrieves them
- **All builds**: Logs are also stored in AsyncStorage for in-app viewing
- **File rotation**: Log files rotate at 5MB, with .old backup created

## Logger Usage

```typescript
import { logger } from '../utils/logger';

logger.info('User logged in', { userId: 123 });
logger.warn('API rate limit approaching', { remaining: 5 });
logger.error('Failed to fetch data', { endpoint: '/api/jobs' }, error);
logger.critical('Database connection failed', { host: 'db.example.com' }, error);
```
